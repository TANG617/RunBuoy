from __future__ import annotations

import json
from dataclasses import replace
from datetime import timedelta

from sqlalchemy import text

from app.heartbeat import WORKER_SERVICE, record_heartbeat
from app.models import ServiceHeartbeat, utcnow
from app.observability import (
    classify_apns_reason,
    metrics,
    readiness_report,
    redact_sensitive,
    request_logger,
)
from tests.conftest import Harness


def _mark_schema_current(harness: Harness) -> None:
    with harness.session_factory() as session:
        session.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
        session.execute(text("INSERT INTO alembic_version (version_num) VALUES ('d001_sync')"))
        session.commit()


def test_healthz_is_liveness_and_readyz_checks_all_dependencies(harness: Harness) -> None:
    assert harness.client.get("/healthz").json() == {"status": "ok", "region": "global"}
    assert harness.client.get("/readyz").status_code == 503

    _mark_schema_current(harness)
    with harness.session_factory() as session:
        record_heartbeat(session, instance_id="worker-a")
        record_heartbeat(
            session,
            instance_id="worker-b",
            status="failed",
            error_code="ProviderUnavailable",
        )

    response = harness.client.get("/readyz")
    assert response.status_code == 200
    report = response.json()
    assert report["status"] == "ready"
    assert report["checks"]["database"] == {"status": "ok"}
    assert report["checks"]["migration"]["current"] == "d001_sync"
    assert report["checks"]["worker"]["fresh_healthy_instances"] == 1
    assert report["checks"]["worker"]["failed_instances"] == 1
    assert "worker-a" not in response.text
    assert "worker-b" not in response.text


def test_readyz_rejects_stale_worker_revision_and_bad_config(harness: Harness) -> None:
    _mark_schema_current(harness)
    with harness.session_factory() as session:
        session.add(
            ServiceHeartbeat(
                service_name=WORKER_SERVICE,
                instance_id="stale-private-instance",
                status="healthy",
                started_at=utcnow() - timedelta(minutes=10),
                last_seen_at=utcnow() - timedelta(minutes=10),
                counters_json={},
            )
        )
        session.execute(text("UPDATE alembic_version SET version_num = '0005'"))
        session.commit()

    response = harness.client.get("/readyz")
    assert response.status_code == 503
    assert response.json()["checks"]["worker"]["status"] == "failed"
    assert response.json()["checks"]["migration"]["status"] == "failed"
    assert "stale-private-instance" not in response.text

    invalid = replace(
        harness.settings,
        deployment_environment="production",
        database_url="sqlite:///secret.db",
    )
    with harness.session_factory() as session:
        ready, report = readiness_report(session, invalid)
    assert ready is False
    assert report["checks"]["configuration"]["status"] == "failed"  # type: ignore[index]
    serialized = json.dumps(report)
    assert "secret.db" not in serialized
    assert invalid.credential_pepper not in serialized
    assert invalid.token_encryption_key not in serialized

    predictable_rate_pepper = replace(
        harness.settings,
        deployment_environment="production",
        database_url="postgresql+psycopg://database/runbuoy",
        credential_pepper="c" * 32,
        token_encryption_key="ZmFrZS1idXQtdW5pcXVlLWZlcm5ldC1rZXktMTIzNDU2Nzg5MA==",
        rate_limit_ip_pepper="runbuoy-development-only-rate-limit-ip-pepper",
    )
    assert "RATE_LIMIT_IP_PEPPER" in predictable_rate_pepper.configuration_errors()


def test_readyz_returns_503_when_heartbeat_table_is_not_migrated(harness: Harness) -> None:
    with harness.session_factory() as session:
        session.execute(text("DROP TABLE service_heartbeats"))
        session.commit()
    response = harness.client.get("/readyz")
    assert response.status_code == 503
    assert response.json()["checks"]["worker"]["status"] == "failed"


def test_request_log_is_json_allowlisted_and_uses_route_template(
    harness: Harness, monkeypatch: object
) -> None:
    logged: list[str] = []
    monkeypatch.setattr(request_logger, "info", logged.append)  # type: ignore[attr-defined]
    secret = "super-secret-bearer-value"
    response = harness.client.get(
        "/v1/runs/00000000-0000-4000-8000-000000000001?token=query-secret",
        headers={"Authorization": f"Bearer {secret}", "X-Request-ID": "request.safe-1"},
    )
    assert response.status_code == 401
    assert response.headers["x-request-id"].startswith("req_")
    event = json.loads(logged[-1])
    assert event["event"] == "http_request"
    assert event["route"] == "/v1/runs/{run_id}"
    assert event["status"] == 401
    assert secret not in logged[-1]
    assert "query-secret" not in logged[-1]
    assert "request.safe-1" not in logged[-1]
    assert "00000000-0000-4000-8000-000000000001" not in logged[-1]

    redacted = redact_sensitive(
        {
            "authorization": secret,
            "nested": {"device_token": "device-secret", "safe": "allowed"},
            "payload": {"title": "private title"},
        }
    )
    assert redacted == {
        "authorization": "[REDACTED]",
        "nested": {"device_token": "[REDACTED]", "safe": "allowed"},
        "payload": "[REDACTED]",
    }


def test_metrics_have_fixed_labels_and_never_export_user_values(harness: Harness) -> None:
    metrics.reset_for_test()
    private_installation = "private-installation-id"
    private_title = "Confidential Optimization Title"
    device, machine = harness.pair(harness.bootstrap(private_installation))
    harness.client.put(
        "/v1/runs/00000000-0000-4000-8000-000000000002",
        headers={"Authorization": f"Bearer {machine['credential']}"},
        json={"machine_id": machine["machine_id"], "title": private_title},
    )
    harness.client.get("/v1/sync", headers={"Authorization": f"Bearer {device['credential']}"})
    metrics.record_rate_limit("/v1/pairing-sessions")
    metrics.record_sync("not_modified")

    response = harness.client.get("/metrics")
    assert response.status_code == 200
    output = response.text
    for name in (
        "runbuoy_http_requests_total",
        "runbuoy_http_request_duration_seconds_bucket",
        "runbuoy_rate_limit_rejections_total",
        "runbuoy_outbox_items",
        "runbuoy_outbox_oldest_pending_age_seconds",
        "runbuoy_apns_responses_total",
        "runbuoy_apns_queue_latency_seconds",
        "runbuoy_apns_provider_latency_seconds",
        "runbuoy_apns_invalid_tokens_total",
        "runbuoy_active_live_activity_bindings",
        "runbuoy_worker_heartbeat_age_seconds",
        "runbuoy_cleanup_deleted_rows_total",
        "runbuoy_sync_requests_total",
    ):
        assert name in output
    assert 'route="/v1/runs/{run_id}"' in output
    assert 'runbuoy_sync_requests_total{outcome="hit"} 1' in output
    assert private_installation not in output
    assert private_title not in output
    assert device["credential"] not in output
    assert machine["credential"] not in output
    assert machine["machine_id"] not in output


def test_apns_reason_classification_is_bounded() -> None:
    assert classify_apns_reason(200, None) == "none"
    assert classify_apns_reason(410, "Unregistered") == "invalid_token"
    assert classify_apns_reason(429, "TooManyRequests") == "throttled"
    assert classify_apns_reason(403, "InvalidProviderToken") == "authentication"
    assert classify_apns_reason(503, "InternalServerError") == "transient"
