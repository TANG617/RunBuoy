from __future__ import annotations

import json
import uuid
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from sqlalchemy import select

from app.apns import (
    APNsRequest,
    APNsResult,
    ProductionAPNsProvider,
    live_activity_expiration,
    live_activity_headers,
)
from app.models import (
    Device,
    LiveActivityBinding,
    PushAttempt,
    PushOutbox,
    Run,
    utcnow,
)
from app.outbox import OutboxProcessor
from app.security import cipher_for, new_id
from app.services import live_payload
from tests.conftest import Harness
from tests.test_api import auth, event, post_events

FIXTURES = Path(__file__).parent / "fixtures"


class ResultProvider:
    def __init__(self, result: APNsResult) -> None:
        self.result = result
        self.requests: list[APNsRequest] = []

    def send(self, request: APNsRequest) -> APNsResult:
        self.requests.append(request)
        return self.result

    def close(self) -> None:
        return None


def _live_run(harness: Harness) -> Run:
    _, machine = harness.pair()
    with harness.session_factory() as session:
        run = Run(
            id="00000000-0000-4000-8000-000000000001",
            workspace_id=machine["workspace_id"],
            machine_id=machine["machine_id"],
            title="Gurobi Experiment",
            execution_status="RUNNING",
            health_status="HEALTHY",
            attention_status="NONE",
            progress={
                "kind": "determinate",
                "fraction": 0.25,
                "current": 25,
                "total": 100,
            },
            phase="solve",
            safe_message="Optimizing",
            created_at=datetime(2026, 7, 26, 12, 0, tzinfo=UTC),
            started_at=datetime(2026, 7, 26, 12, 0, tzinfo=UTC),
            updated_at=datetime(2026, 7, 26, 12, 0, tzinfo=UTC),
            last_seq=7,
        )
        session.add(run)
        session.commit()
        session.refresh(run)
        session.expunge(run.machine)
        session.expunge(run)
        return run


def test_exact_live_activity_start_payload_and_headers(harness: Harness) -> None:
    run = _live_run(harness)
    now = datetime(2026, 7, 26, 12, 0, tzinfo=UTC)
    payload = live_payload(run, "LIVE_START", now, machine_name="Studio Mac")
    expected = json.loads((FIXTURES / "live_start.json").read_text())
    assert payload == expected
    assert payload["aps"]["attributes-type"] == "RunActivityAttributes"
    assert set(payload["aps"]["attributes"]) == {
        "runID",
        "title",
        "machineName",
        "schemaVersion",
    }
    assert "alert" in payload["aps"]
    assert payload["aps"]["input-push-token"] == 1
    expiration = live_activity_expiration(payload, now=int(now.timestamp()))
    assert expiration == int(now.timestamp()) + 300
    assert live_activity_headers(harness.settings, 5, expiration=expiration) == {
        "apns-push-type": "liveactivity",
        "apns-topic": "dev.runbuoy.app.push-type.liveactivity",
        "apns-priority": "5",
        "apns-expiration": str(int(now.timestamp()) + 300),
    }


def test_update_end_stale_and_default_dismissal(harness: Harness) -> None:
    run = _live_run(harness)
    now = datetime(2026, 7, 26, 12, 0, tzinfo=UTC)
    delivered_at = now + timedelta(seconds=30)
    update = live_payload(run, "LIVE_UPDATE", delivered_at, machine_name="Studio Mac")
    assert update["aps"]["event"] == "update"
    assert update["aps"]["stale-date"] == int((now + timedelta(seconds=60)).timestamp())
    assert live_activity_expiration(update, now=int(now.timestamp())) == int(
        (now + timedelta(seconds=60)).timestamp()
    )
    assert "dismissal-date" not in update["aps"]

    run.execution_status = "FAILED"
    run.ended_at = now
    ended = live_payload(run, "LIVE_END", now, machine_name="Studio Mac")
    assert ended["aps"]["event"] == "end"
    assert ended["aps"]["content-state"]["endedAt"] == now.isoformat()
    assert "stale-date" not in ended["aps"]
    assert "dismissal-date" not in ended["aps"]
    assert live_activity_expiration(ended, now=int(now.timestamp())) == int(
        (now + timedelta(hours=4)).timestamp()
    )


def test_heartbeat_enqueues_live_update_with_fresh_timestamp(harness: Harness) -> None:
    device, machine = harness.pair()
    run_id = str(uuid.uuid4())
    harness.register_run(machine, run_id)
    started_at = datetime.now(UTC) - timedelta(seconds=30)
    assert (
        post_events(
            harness,
            machine,
            run_id,
            [event(run_id, machine["machine_id"], 1, "run.started", at=started_at)],
        ).status_code
        == 200
    )
    assert (
        harness.client.put(
            "/v1/live-activities/activity-heartbeat/update-token",
            headers=auth(device["credential"]),
            json={
                "token": "heartbeat-update-token",
                "device_id": device["device_id"],
                "run_id": run_id,
                "generation": 1,
            },
        ).status_code
        == 204
    )

    heartbeat_at = started_at + timedelta(seconds=15)
    assert (
        post_events(
            harness,
            machine,
            run_id,
            [event(run_id, machine["machine_id"], 2, "run.heartbeat", at=heartbeat_at)],
        ).status_code
        == 200
    )
    with harness.session_factory() as session:
        update = session.scalar(
            select(PushOutbox).where(
                PushOutbox.run_id == run_id,
                PushOutbox.kind == "LIVE_UPDATE",
            )
        )
        assert update is not None
        assert update.status == "pending"
        assert (
            update.desired_payload["aps"]["content-state"]["updatedAt"] == heartbeat_at.isoformat()
        )


def test_machine_rename_updates_active_live_activity_content(harness: Harness) -> None:
    device, machine = harness.pair()
    run_id = str(uuid.uuid4())
    harness.register_run(machine, run_id)
    created_at = datetime.now(UTC) - timedelta(seconds=30)
    assert (
        post_events(
            harness,
            machine,
            run_id,
            [
                event(run_id, machine["machine_id"], 1, "run.created", at=created_at),
                event(run_id, machine["machine_id"], 2, "run.started", at=created_at),
            ],
        ).status_code
        == 200
    )
    assert (
        harness.client.put(
            "/v1/live-activities/activity-rename/update-token",
            headers=auth(device["credential"]),
            json={
                "token": "rename-update-token",
                "device_id": device["device_id"],
                "run_id": run_id,
                "generation": 1,
            },
        ).status_code
        == 204
    )

    renamed = harness.client.patch(
        f"/v1/machines/{machine['machine_id']}",
        headers=auth(machine["credential"]),
        json={"display_name": "Build Mac"},
    )
    assert renamed.status_code == 200, renamed.text
    with harness.session_factory() as session:
        update = session.scalar(
            select(PushOutbox).where(
                PushOutbox.run_id == run_id,
                PushOutbox.kind == "LIVE_UPDATE",
            )
        )
        assert update is not None
        assert update.desired_payload["aps"]["content-state"]["machineName"] == "Build Mac"


def test_outbox_mock_send_records_payload_without_secrets(harness: Harness) -> None:
    device, machine = harness.pair()
    harness.client.put(
        f"/v1/devices/{device['device_id']}/push-to-start-token",
        headers=auth(device["credential"]),
        json={"token": "sensitive-push-token"},
    )
    run_id = str(uuid.uuid4())
    harness.register_run(machine, run_id)
    old = datetime.now(UTC) - timedelta(seconds=10)
    assert (
        post_events(
            harness,
            machine,
            run_id,
            [event(run_id, machine["machine_id"], 1, "run.started", at=old)],
        ).status_code
        == 200
    )
    provider = ResultProvider(APNsResult(200, "accepted-id"))
    processor = OutboxProcessor(harness.settings, provider, cipher_for(harness.settings))
    with harness.session_factory() as session:
        assert processor.drain(session) == 1
        attempt = session.scalar(select(PushAttempt))
        assert attempt is not None
        assert attempt.request_payload["aps"]["event"] == "start"
        assert attempt.queue_latency_ms is not None
        assert attempt.queue_latency_ms >= 0
        assert attempt.provider_latency_ms is not None
        assert attempt.provider_latency_ms >= 0
        assert "authorization" not in attempt.request_headers
        assert int(attempt.request_headers["apns-expiration"]) > int(old.timestamp())
        assert "sensitive-push-token" not in json.dumps(attempt.request_payload)
    assert provider.requests[0].token == "sensitive-push-token"


def test_apns_410_invalidates_activity_token(harness: Harness) -> None:
    device, machine = harness.pair()
    run_id = str(uuid.uuid4())
    harness.register_run(machine, run_id)
    with harness.session_factory() as session:
        binding = LiveActivityBinding(
            id=new_id("lab"),
            run_id=run_id,
            device_id=device["device_id"],
            activity_id="activity-1",
            update_push_token_encrypted=cipher_for(harness.settings).encrypt("update-token"),
            token_generation=1,
        )
        session.add(binding)
        session.flush()
        outbox = PushOutbox(
            id=new_id("out"),
            kind="LIVE_UPDATE",
            target_type="activity",
            target_id=binding.id,
            run_id=run_id,
            desired_payload={"aps": {"event": "update"}},
            priority=5,
            available_at=utcnow(),
            status="pending",
            coalesce_key="test-410",
        )
        session.add(outbox)
        session.commit()
        binding_id = binding.id
    provider = ResultProvider(APNsResult(410, reason="Unregistered"))
    processor = OutboxProcessor(harness.settings, provider, cipher_for(harness.settings))
    with harness.session_factory() as session:
        assert processor.process_one(session)
        fetched_binding = session.get(LiveActivityBinding, binding_id)
        assert fetched_binding is not None
        assert fetched_binding.state == "invalidated"
        assert fetched_binding.update_push_token_encrypted is None
        assert fetched_binding.invalidated_at is not None


def test_expired_end_releases_server_binding(harness: Harness) -> None:
    device, machine = harness.pair()
    run_id = str(uuid.uuid4())
    harness.register_run(machine, run_id)
    expired_at = datetime.now(UTC) - timedelta(hours=5)
    with harness.session_factory() as session:
        binding = LiveActivityBinding(
            id=new_id("lab"),
            run_id=run_id,
            device_id=device["device_id"],
            activity_id="activity-expired-end",
            update_push_token_encrypted=cipher_for(harness.settings).encrypt("update-token"),
            token_generation=1,
        )
        session.add(binding)
        session.add(
            PushOutbox(
                id=new_id("out"),
                kind="LIVE_END",
                target_type="activity",
                target_id=binding.id,
                run_id=run_id,
                desired_payload={"aps": {"event": "end", "timestamp": int(expired_at.timestamp())}},
                priority=10,
                available_at=utcnow(),
                status="pending",
                coalesce_key="expired-end",
            )
        )
        session.commit()
        binding_id = binding.id
    provider = ResultProvider(APNsResult(200))
    processor = OutboxProcessor(harness.settings, provider, cipher_for(harness.settings))
    with harness.session_factory() as session:
        assert processor.process_one(session)
        binding = session.get(LiveActivityBinding, binding_id)
        assert binding is not None
        assert binding.state == "expired"
        assert binding.ended_at is not None
    assert provider.requests == []


def test_outbox_retry_is_bounded(harness: Harness) -> None:
    device = harness.bootstrap()
    harness.client.put(
        f"/v1/devices/{device['device_id']}/notification-token",
        headers=auth(device["credential"]),
        json={"token": "normal-token"},
    )
    with harness.session_factory() as session:
        item = PushOutbox(
            id=new_id("out"),
            kind="NOTIFICATION",
            target_type="device",
            target_id=device["device_id"],
            desired_payload={"aps": {"alert": {"title": "x", "body": "y"}}},
            priority=10,
            available_at=utcnow(),
            status="pending",
            coalesce_key="retry",
            attempt_count=harness.settings.outbox_max_attempts - 1,
        )
        session.add(item)
        session.commit()
        item_id = item.id
    provider = ResultProvider(APNsResult(503, reason="ServiceUnavailable"))
    processor = OutboxProcessor(harness.settings, provider, cipher_for(harness.settings))
    with harness.session_factory() as session:
        processor.process_one(session)
        fetched_item = session.get(PushOutbox, item_id)
        assert fetched_item is not None
        assert fetched_item.status == "failed"
        assert fetched_item.attempt_count == harness.settings.outbox_max_attempts


def test_per_device_max_two_live_activities(harness: Harness) -> None:
    device, machine = harness.pair()
    harness.client.put(
        f"/v1/devices/{device['device_id']}/push-to-start-token",
        headers=auth(device["credential"]),
        json={"token": "push-token"},
    )
    now = datetime.now(UTC) - timedelta(seconds=10)
    for _sequence in range(3):
        run_id = str(uuid.uuid4())
        harness.register_run(machine, run_id)
        assert (
            post_events(
                harness,
                machine,
                run_id,
                [event(run_id, machine["machine_id"], 1, "run.started", at=now)],
            ).status_code
            == 200
        )
    provider = ResultProvider(APNsResult(200))
    processor = OutboxProcessor(harness.settings, provider, cipher_for(harness.settings))
    with harness.session_factory() as session:
        assert processor.drain(session) == 3
        statuses = list(session.scalars(select(PushOutbox.status)))
        assert statuses.count("sent") == 2
        assert statuses.count("suppressed") == 1
        active = list(
            session.scalars(
                select(LiveActivityBinding).where(LiveActivityBinding.state == "active")
            )
        )
        assert len(active) == 2


def test_token_rotation_keeps_latest_generation(harness: Harness) -> None:
    device = harness.bootstrap()
    for generation, token in [(1, "token-generation-one"), (2, "token-generation-two")]:
        response = harness.client.put(
            f"/v1/devices/{device['device_id']}/push-to-start-token",
            headers=auth(device["credential"]),
            json={"token": token, "generation": generation},
        )
        assert response.status_code == 204
    with harness.session_factory() as session:
        stored = session.get(Device, device["device_id"])
        assert stored is not None
        assert stored.push_to_start_token_generation == 2
        assert (
            cipher_for(harness.settings).decrypt(stored.push_to_start_token_encrypted or "")
            == "token-generation-two"
        )
    stale = harness.client.put(
        f"/v1/devices/{device['device_id']}/push-to-start-token",
        headers=auth(device["credential"]),
        json={"token": "stale-token-value", "generation": 1},
    )
    assert stale.status_code == 409


def test_stale_activity_sync_catches_up_and_remains_deliverable(harness: Harness) -> None:
    device, machine = harness.pair()
    run_id = str(uuid.uuid4())
    harness.register_run(machine, run_id)
    started = datetime.now(UTC) - timedelta(seconds=30)
    assert (
        post_events(
            harness,
            machine,
            run_id,
            [event(run_id, machine["machine_id"], 1, "run.started", at=started)],
        ).status_code
        == 200
    )
    assert (
        harness.client.put(
            "/v1/live-activities/activity-stale/update-token",
            headers=auth(device["credential"]),
            json={
                "token": "stale-update-token",
                "device_id": device["device_id"],
                "run_id": run_id,
                "generation": 1,
            },
        ).status_code
        == 204
    )
    assert (
        post_events(
            harness,
            machine,
            run_id,
            [
                event(
                    run_id,
                    machine["machine_id"],
                    2,
                    "run.progress",
                    at=started + timedelta(seconds=15),
                    payload={"progress": {"kind": "determinate", "fraction": 0.5}},
                )
            ],
        ).status_code
        == 200
    )

    synced = harness.client.post(
        f"/v1/devices/{device['device_id']}/activity-sync",
        headers=auth(device["credential"]),
        json={
            "frequent_pushes_enabled": False,
            "activities": [
                {
                    "activity_id": "activity-stale",
                    "run_id": run_id,
                    "update_token": "stale-update-token",
                    "token_generation": 1,
                    "state": "stale",
                    "last_sequence": 1,
                }
            ],
        },
    )
    assert synced.status_code == 204
    with harness.session_factory() as session:
        binding = session.scalar(
            select(LiveActivityBinding).where(LiveActivityBinding.activity_id == "activity-stale")
        )
        assert binding is not None
        assert binding.state == "stale"
        assert binding.ended_at is None
        device_model = session.get(Device, device["device_id"])
        assert device_model is not None
        assert not device_model.frequent_live_activity_updates_enabled
        pending = session.scalar(
            select(PushOutbox).where(
                PushOutbox.target_id == binding.id,
                PushOutbox.status == "pending",
            )
        )
        assert pending is not None
        assert pending.desired_payload["aps"]["content-state"]["sequence"] == 2

    assert (
        post_events(
            harness,
            machine,
            run_id,
            [event(run_id, machine["machine_id"], 3, "run.failed")],
        ).status_code
        == 200
    )
    with harness.session_factory() as session:
        pending = session.scalar(select(PushOutbox).where(PushOutbox.status == "pending"))
        assert pending is not None
        assert pending.kind == "LIVE_END"
        assert pending.desired_payload["aps"]["content-state"]["sequence"] == 3


def test_start_terminal_then_late_update_token_enqueues_end(harness: Harness) -> None:
    device, machine = harness.pair()
    harness.client.put(
        f"/v1/devices/{device['device_id']}/push-to-start-token",
        headers=auth(device["credential"]),
        json={"token": "push-token"},
    )
    run_id = str(uuid.uuid4())
    harness.register_run(machine, run_id)
    start = datetime.now(UTC) - timedelta(seconds=20)
    assert (
        post_events(
            harness,
            machine,
            run_id,
            [event(run_id, machine["machine_id"], 1, "run.started", at=start)],
        ).status_code
        == 200
    )
    provider = ResultProvider(APNsResult(200))
    processor = OutboxProcessor(harness.settings, provider, cipher_for(harness.settings))
    with harness.session_factory() as session:
        assert processor.process_one(session)
    assert (
        post_events(
            harness,
            machine,
            run_id,
            [
                event(
                    run_id,
                    machine["machine_id"],
                    2,
                    "run.failed",
                    at=start + timedelta(seconds=10),
                )
            ],
        ).status_code
        == 200
    )
    with harness.session_factory() as session:
        assert (
            session.scalar(
                select(PushOutbox).where(
                    PushOutbox.kind == "LIVE_END", PushOutbox.status == "pending"
                )
            )
            is None
        )
    registered = harness.client.put(
        "/v1/live-activities/activity-late/update-token",
        headers=auth(device["credential"]),
        json={
            "token": "late-update-token",
            "device_id": device["device_id"],
            "run_id": run_id,
            "generation": 1,
        },
    )
    assert registered.status_code == 204
    with harness.session_factory() as session:
        pending_end = session.scalar(
            select(PushOutbox).where(PushOutbox.kind == "LIVE_END", PushOutbox.status == "pending")
        )
        assert pending_end is not None
        assert pending_end.priority == 10


def test_immediate_start_for_short_run_still_enqueues_end(harness: Harness) -> None:
    device, machine = harness.pair()
    harness.client.put(
        f"/v1/devices/{device['device_id']}/push-to-start-token",
        headers=auth(device["credential"]),
        json={"token": "immediate-push-token"},
    )
    run_id = str(uuid.uuid4())
    harness.register_run(machine, run_id, live_activity_policy="immediate")
    started_at = datetime.now(UTC)
    assert (
        post_events(
            harness,
            machine,
            run_id,
            [event(run_id, machine["machine_id"], 1, "run.started", at=started_at)],
        ).status_code
        == 200
    )
    provider = ResultProvider(APNsResult(200))
    processor = OutboxProcessor(harness.settings, provider, cipher_for(harness.settings))
    with harness.session_factory() as session:
        start = session.scalar(select(PushOutbox).where(PushOutbox.kind == "LIVE_START"))
        assert start is not None
        assert start.available_at.replace(tzinfo=UTC) <= datetime.now(UTC)
        assert processor.process_one(session)

    assert (
        harness.client.put(
            "/v1/live-activities/activity-immediate/update-token",
            headers=auth(device["credential"]),
            json={
                "token": "immediate-update-token",
                "device_id": device["device_id"],
                "run_id": run_id,
                "generation": 1,
            },
        ).status_code
        == 204
    )
    assert (
        post_events(
            harness,
            machine,
            run_id,
            [
                event(
                    run_id,
                    machine["machine_id"],
                    2,
                    "run.succeeded",
                    at=started_at + timedelta(seconds=2),
                )
            ],
        ).status_code
        == 200
    )
    with harness.session_factory() as session:
        pending_end = session.scalar(
            select(PushOutbox).where(
                PushOutbox.kind == "LIVE_END",
                PushOutbox.status == "pending",
            )
        )
        assert pending_end is not None
        assert pending_end.priority == 10


def test_multiple_updates_then_end_reuse_coalesce_key(harness: Harness) -> None:
    device, machine = harness.pair()
    run_id = str(uuid.uuid4())
    harness.register_run(machine, run_id)
    now = datetime.now(UTC) - timedelta(seconds=30)
    assert (
        post_events(
            harness,
            machine,
            run_id,
            [event(run_id, machine["machine_id"], 1, "run.started", at=now)],
        ).status_code
        == 200
    )
    assert (
        harness.client.put(
            "/v1/live-activities/activity-sequence/update-token",
            headers=auth(device["credential"]),
            json={
                "token": "update-sequence-token",
                "device_id": device["device_id"],
                "run_id": run_id,
                "generation": 1,
            },
        ).status_code
        == 204
    )
    provider = ResultProvider(APNsResult(200))
    processor = OutboxProcessor(harness.settings, provider, cipher_for(harness.settings))
    for seq, fraction, event_type in [
        (2, 0.2, "run.progress"),
        (3, 0.4, "run.progress"),
        (4, None, "run.succeeded"),
    ]:
        payload = (
            {
                "progress": {
                    "kind": "determinate",
                    "current": fraction * 100,
                    "total": 100,
                    "fraction": fraction,
                }
            }
            if fraction is not None
            else {}
        )
        response = post_events(
            harness,
            machine,
            run_id,
            [
                event(
                    run_id,
                    machine["machine_id"],
                    seq,
                    event_type,
                    at=now + timedelta(seconds=seq * 5),
                    payload=payload,
                )
            ],
        )
        assert response.status_code == 200, response.text
        with harness.session_factory() as session:
            pending = session.scalar(select(PushOutbox).where(PushOutbox.status == "pending"))
            assert pending is not None
            pending.available_at = utcnow() - timedelta(seconds=1)
            session.commit()
            assert processor.process_one(session)
    assert [request.payload["aps"]["event"] for request in provider.requests] == [
        "update",
        "update",
        "end",
    ]


def test_production_provider_es256_jwt_and_http_request(harness: Harness) -> None:
    key = ec.generate_private_key(ec.SECP256R1())
    pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        return httpx.Response(200, headers={"apns-id": "id-1"})

    settings = replace(
        harness.settings,
        apns_mode="production",
        apns_key_id="ABCDEFGHIJ",
        apns_team_id="KLMNOPQRST",
        apns_private_key=pem,
    )
    provider = ProductionAPNsProvider(
        settings,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    result = provider.send(
        APNsRequest(
            token="device-token",
            payload={"aps": {"alert": {"title": "T", "body": "B"}}},
            headers={"apns-topic": settings.apns_bundle_id, "apns-push-type": "alert"},
        )
    )
    assert result.accepted
    request = captured["request"]
    assert request.url.path == "/3/device/device-token"
    raw_jwt = request.headers["authorization"].removeprefix("bearer ")
    assert jwt.get_unverified_header(raw_jwt) == {
        "alg": "ES256",
        "kid": "ABCDEFGHIJ",
        "typ": "JWT",
    }
    claims = jwt.decode(raw_jwt, options={"verify_signature": False})
    assert claims["iss"] == "KLMNOPQRST"
    provider.close()


def test_production_provider_turns_network_errors_into_retryable_result(
    harness: Harness,
) -> None:
    key = ec.generate_private_key(ec.SECP256R1())
    pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("temporary APNs connection failure", request=request)

    settings = replace(
        harness.settings,
        apns_mode="production",
        apns_key_id="ABCDEFGHIJ",
        apns_team_id="KLMNOPQRST",
        apns_private_key=pem,
    )
    provider = ProductionAPNsProvider(
        settings,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    result = provider.send(
        APNsRequest(
            token="device-token",
            payload={"aps": {"event": "update"}},
            headers={"apns-topic": settings.apns_bundle_id},
        )
    )

    assert result.status_code == 503
    assert result.reason == "ConnectError"
    assert result.retryable
    provider.close()
