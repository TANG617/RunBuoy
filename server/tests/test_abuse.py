from __future__ import annotations

import asyncio
import uuid
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi import HTTPException, Request, Response
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, event, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app import abuse
from app.abuse import (
    anonymized_key,
    cleanup_abuse_state,
    client_ip,
    enforce_rate_limit,
)
from app.config import Settings
from app.database import Base, get_session
from app.main import create_app
from app.models import Notification, PairingSession, QuotaLock, RateLimitBucket
from tests.conftest import Harness
from tests.test_api import auth, post_events
from tests.test_api import event as run_event


@contextmanager
def configured_harness(tmp_path: Path, settings: Settings) -> Generator[Harness, None, None]:
    database_path = tmp_path / f"{uuid.uuid4()}.db"
    configured = replace(settings, database_url=f"sqlite:///{database_path}")
    engine: Engine = create_engine(
        configured.database_url,
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def enforce_foreign_keys(dbapi_connection: Any, _connection_record: Any) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False, class_=Session)
    app = create_app(configured)

    def override_session() -> Generator[Session, None, None]:
        with factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    with TestClient(app) as client:
        yield Harness(client, factory, configured)
    Base.metadata.drop_all(engine)
    engine.dispose()


def _pair_machine(
    harness: Harness,
    device: dict[str, str],
    machine_id: str,
) -> tuple[dict[str, Any], Any]:
    created = harness.client.post(
        "/v1/pairing-sessions",
        json={"machine_id": machine_id, "display_name": machine_id},
    )
    assert created.status_code == 201, created.text
    pairing = created.json()
    claimed = harness.client.post(
        f"/v1/pairing-sessions/{pairing['pairing_session_id']}/claim",
        headers=auth(device["credential"]),
        json={"challenge": pairing["challenge"]},
    )
    if claimed.status_code != 200:
        return pairing, claimed
    exchanged = harness.client.post(
        f"/v1/pairing-sessions/{pairing['pairing_session_id']}/exchange",
        json={"exchange_secret": pairing["exchange_secret"]},
    )
    assert exchanged.status_code == 200, exchanged.text
    return {**pairing, **exchanged.json()}, claimed


def _request(peer: str, forwarded: str | None = None) -> Request:
    headers = []
    if forwarded is not None:
        headers.append((b"x-forwarded-for", forwarded.encode()))
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": headers,
            "client": (peer, 1234),
        }
    )


def test_trusted_proxy_boundary_and_hmac_anonymization() -> None:
    settings = Settings(trusted_proxy_cidrs=("10.0.0.0/8", "192.0.2.10/32"))
    assert client_ip(_request("203.0.113.8", "198.51.100.7"), settings) == "203.0.113.8"
    assert (
        client_ip(
            _request("10.0.0.2", "198.51.100.7, 192.0.2.10"),
            settings,
        )
        == "198.51.100.7"
    )
    assert client_ip(_request("10.0.0.2", "not-an-ip"), settings) == "10.0.0.2"

    key = anonymized_key(settings, "ip", "198.51.100.7")
    assert len(key) == 64
    assert "198.51.100.7" not in key
    assert key != anonymized_key(
        replace(settings, rate_limit_ip_pepper="other"), "ip", "198.51.100.7"
    )


def test_stream_without_content_length_is_rejected_before_routing(tmp_path: Path) -> None:
    settings = Settings(max_request_body_bytes=32)
    app = create_app(settings)
    messages = [
        {"type": "http.request", "body": b"{" + b"x" * 20, "more_body": True},
        {"type": "http.request", "body": b"x" * 20 + b"}", "more_body": False},
    ]
    sent: list[dict[str, Any]] = []
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/v1/devices/bootstrap",
        "raw_path": b"/v1/devices/bootstrap",
        "query_string": b"",
        "headers": [(b"content-type", b"application/json")],
        "client": ("203.0.113.1", 1234),
        "server": ("testserver", 80),
    }

    async def receive() -> dict[str, Any]:
        return messages.pop(0)

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    asyncio.run(app(scope, receive, send))  # type: ignore[arg-type]
    assert sent[0]["status"] == 413
    assert b"request_body_too_large" in sent[1]["body"]

    with configured_harness(tmp_path, settings) as harness:
        assert harness.client.get("/healthz").status_code == 200


def test_rate_limit_429_has_stable_metadata_and_no_plain_ip(tmp_path: Path) -> None:
    settings = Settings(rate_limit_device_bootstrap_per_hour=2)
    with configured_harness(tmp_path, settings) as harness:
        accepted = [harness.bootstrap(f"ios-{index}") for index in range(2)]
        assert len(accepted) == 2
        response = harness.client.post(
            "/v1/devices/bootstrap",
            json={"installation_id": "ios-rejected"},
        )
        assert response.status_code == 429
        assert response.headers["retry-after"].isdigit()
        assert response.headers["x-ratelimit-bucket"] == "device_bootstrap"
        assert response.headers["x-ratelimit-limit"] == "2"
        assert response.headers["x-ratelimit-remaining"] == "0"
        assert response.headers["x-ratelimit-reset"].isdigit()
        assert response.json()["detail"]["code"] == "rate_limit_exceeded"
        with harness.session_factory() as session:
            buckets = list(session.scalars(select(RateLimitBucket)))
            assert len(buckets) == 1
            assert buckets[0].request_count == 3
            assert "testclient" not in buckets[0].subject_key


def test_rate_limiter_failure_policy_is_explicit(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(*_args: Any, **_kwargs: Any) -> int:
        raise SQLAlchemyError("accounting unavailable")

    monkeypatch.setattr(abuse, "_increment_bucket", fail)
    with harness.session_factory() as session:
        with pytest.raises(HTTPException) as error:
            enforce_rate_limit(
                session,
                harness.settings,
                Response(),
                bucket_name="test",
                subject_key="subject",
                limit=1,
                window_seconds=60,
            )
        assert error.value.status_code == 503

    with harness.session_factory() as session:
        response = Response()
        result = enforce_rate_limit(
            session,
            replace(harness.settings, rate_limit_fail_open=True),
            response,
            bucket_name="test",
            subject_key="subject",
            limit=1,
            window_seconds=60,
        )
        assert result is None
        assert response.headers["x-ratelimit-policy"] == "fail-open"


def test_pending_pairing_quota_releases_expired_sessions(tmp_path: Path) -> None:
    settings = Settings(max_pending_pairings_per_ip=1)
    with configured_harness(tmp_path, settings) as harness:
        first = harness.client.post("/v1/pairing-sessions", json={"display_name": "one"})
        assert first.status_code == 201
        full = harness.client.post("/v1/pairing-sessions", json={"display_name": "two"})
        assert full.status_code == 409
        assert full.json()["detail"] == {
            "code": "resource_quota_exceeded",
            "resource": "pending_pairing_sessions",
            "scope": "anonymized_ip",
            "limit": 1,
        }
        with harness.session_factory() as session:
            pairing = session.get(PairingSession, first.json()["pairing_session_id"])
            assert pairing is not None
            pairing.expires_at = datetime.now(UTC) - timedelta(seconds=1)
            session.commit()
        assert (
            harness.client.post("/v1/pairing-sessions", json={"display_name": "two"}).status_code
            == 201
        )


def test_machine_quota_is_workspace_scoped(tmp_path: Path) -> None:
    settings = Settings(max_machines_per_workspace=1)
    with configured_harness(tmp_path, settings) as harness:
        first_device = harness.bootstrap("workspace-one")
        _, claimed = _pair_machine(harness, first_device, "machine-one")
        assert claimed.status_code == 200
        _, rejected = _pair_machine(harness, first_device, "machine-two")
        assert rejected.status_code == 409
        assert rejected.json()["detail"]["resource"] == "machines"

        second_device = harness.bootstrap("workspace-two")
        _, other_claimed = _pair_machine(harness, second_device, "machine-three")
        assert other_claimed.status_code == 200


def test_active_run_quota_allows_terminal_replacement_and_offline_batch(
    tmp_path: Path,
) -> None:
    settings = Settings(max_active_runs_per_machine=1, max_events_per_batch=100)
    with configured_harness(tmp_path, settings) as harness:
        _, machine = harness.pair()
        first_run = str(uuid.uuid4())
        second_run = str(uuid.uuid4())
        harness.register_run(machine, first_run)
        rejected = harness.client.put(
            f"/v1/runs/{second_run}",
            headers=auth(machine["credential"]),
            json={"machine_id": machine["machine_id"], "title": "queued"},
        )
        assert rejected.status_code == 409
        assert rejected.json()["detail"]["resource"] == "active_runs"

        terminal = post_events(
            harness,
            machine,
            first_run,
            [run_event(first_run, machine["machine_id"], 1, "run.failed")],
        )
        assert terminal.status_code == 200
        harness.register_run(machine, second_run)

        offline_events = [
            run_event(
                second_run,
                machine["machine_id"],
                sequence,
                "run.heartbeat",
                at=datetime.now(UTC) + timedelta(seconds=15 * sequence),
            )
            for sequence in range(1, 101)
        ]
        replay = post_events(harness, machine, second_run, offline_events)
        assert replay.status_code == 200, replay.text
        assert replay.json()["last_seq"] == 100


def test_configurable_event_batch_quota_has_clear_413(tmp_path: Path) -> None:
    settings = Settings(max_events_per_batch=1)
    with configured_harness(tmp_path, settings) as harness:
        _, machine = harness.pair()
        run_id = str(uuid.uuid4())
        harness.register_run(machine, run_id)
        response = post_events(
            harness,
            machine,
            run_id,
            [
                run_event(run_id, machine["machine_id"], 1, "run.heartbeat"),
                run_event(run_id, machine["machine_id"], 2, "run.heartbeat"),
            ],
        )
        assert response.status_code == 413
        assert response.json()["detail"] == {
            "code": "event_batch_too_large",
            "limit": 1,
            "actual": 2,
        }


def test_webhook_and_notification_quotas_are_scoped_and_idempotent(tmp_path: Path) -> None:
    settings = Settings(
        max_webhooks_per_workspace=1,
        max_notifications_per_workspace_day=2,
        rate_limit_notification_per_minute=10,
    )
    with configured_harness(tmp_path, settings) as harness:
        _, machine = harness.pair()
        first_hook = harness.client.post(
            "/v1/webhooks",
            headers=auth(machine["credential"]),
            json={"name": "first"},
        )
        assert first_hook.status_code == 201
        full = harness.client.post(
            "/v1/webhooks",
            headers=auth(machine["credential"]),
            json={"name": "second"},
        )
        assert full.status_code == 409
        assert full.json()["detail"]["resource"] == "webhooks"

        first = harness.client.post(
            "/v1/notifications",
            headers={**auth(machine["credential"]), "Idempotency-Key": "same"},
            json={"title": "one", "body": "one"},
        )
        duplicate = harness.client.post(
            "/v1/notifications",
            headers={**auth(machine["credential"]), "Idempotency-Key": "same"},
            json={"title": "one", "body": "one"},
        )
        second = harness.client.post(
            "/v1/notifications",
            headers=auth(machine["credential"]),
            json={"title": "two", "body": "two"},
        )
        exceeded = harness.client.post(
            "/v1/notifications",
            headers=auth(machine["credential"]),
            json={"title": "three", "body": "three"},
        )
        assert first.status_code == duplicate.status_code == second.status_code == 201
        assert first.json()["id"] == duplicate.json()["id"]
        assert exceeded.status_code == 429
        assert exceeded.json()["detail"]["scope"] == "workspace_day"

        other_device = harness.bootstrap("other-workspace")
        other_machine, claimed = _pair_machine(harness, other_device, "other-machine")
        assert claimed.status_code == 200
        other = harness.client.post(
            "/v1/notifications",
            headers=auth(other_machine["credential"]),
            json={"title": "allowed", "body": "allowed"},
        )
        assert other.status_code == 201


def test_webhook_notification_bucket_returns_429(tmp_path: Path) -> None:
    settings = Settings(rate_limit_notification_per_minute=1)
    with configured_harness(tmp_path, settings) as harness:
        _, machine = harness.pair()
        hook = harness.client.post(
            "/v1/webhooks",
            headers=auth(machine["credential"]),
            json={"name": "limited"},
        ).json()
        headers = auth(hook["secret"])
        first = harness.client.post(
            f"/v1/hooks/{hook['hook_id']}/notifications",
            headers=headers,
            json={"title": "one", "body": "one"},
        )
        second = harness.client.post(
            f"/v1/hooks/{hook['hook_id']}/notifications",
            headers=headers,
            json={"title": "two", "body": "two"},
        )
        assert first.status_code == 201
        assert second.status_code == 429
        assert second.headers["x-ratelimit-bucket"] == "notification"


def test_notification_quota_does_not_block_terminal_projection(tmp_path: Path) -> None:
    settings = Settings(max_notifications_per_workspace_day=1)
    with configured_harness(tmp_path, settings) as harness:
        _, machine = harness.pair()
        first = harness.client.post(
            "/v1/notifications",
            headers=auth(machine["credential"]),
            json={"title": "quota", "body": "filled"},
        )
        assert first.status_code == 201
        run_id = str(uuid.uuid4())
        harness.register_run(machine, run_id)
        terminal = post_events(
            harness,
            machine,
            run_id,
            [run_event(run_id, machine["machine_id"], 1, "run.failed")],
        )
        assert terminal.status_code == 200
        assert terminal.json()["snapshot"]["execution_status"] == "FAILED"
        with harness.session_factory() as session:
            assert session.scalar(select(func.count()).select_from(Notification)) == 1


def test_default_event_bucket_allows_documented_burst(harness: Harness) -> None:
    now = datetime(2026, 8, 7, 12, 0, tzinfo=UTC)
    subject = anonymized_key(harness.settings, "machine", "machine-burst")
    with harness.session_factory() as session:
        for _ in range(240):
            enforce_rate_limit(
                session,
                harness.settings,
                Response(),
                bucket_name="event_batch",
                subject_key=subject,
                limit=harness.settings.rate_limit_event_batch_per_minute,
                window_seconds=60,
                now=now,
            )
        with pytest.raises(HTTPException) as error:
            enforce_rate_limit(
                session,
                harness.settings,
                Response(),
                bucket_name="event_batch",
                subject_key=subject,
                limit=harness.settings.rate_limit_event_batch_per_minute,
                window_seconds=60,
                now=now,
            )
        assert error.value.status_code == 429


def test_abuse_cleanup_removes_expired_buckets_and_stale_locks(harness: Harness) -> None:
    now = datetime.now(UTC)
    with harness.session_factory() as session:
        session.add(
            RateLimitBucket(
                bucket_name="expired",
                subject_key="a" * 64,
                window_start=1,
                request_count=1,
                expires_at=now - timedelta(seconds=1),
                updated_at=now - timedelta(hours=2),
            )
        )
        session.add(
            QuotaLock(
                lock_key="test:" + "b" * 64,
                last_used_at=now - timedelta(hours=2),
            )
        )
        session.commit()
        result = cleanup_abuse_state(session, harness.settings, now=now)
        session.commit()
        assert result == {"rate_limit_buckets": 1, "quota_locks": 1}
        assert session.scalar(select(func.count()).select_from(RateLimitBucket)) == 0
        assert session.scalar(select(func.count()).select_from(QuotaLock)) == 0
