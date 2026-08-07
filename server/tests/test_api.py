from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import httpx
from fastapi import FastAPI
from sqlalchemy import select

from app.models import (
    Device,
    Machine,
    Notification,
    PairingSession,
    PushOutbox,
    Run,
    RunEvent,
)
from tests.conftest import Harness


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def event(
    run_id: str,
    machine_id: str,
    seq: int,
    event_type: str,
    *,
    at: datetime | None = None,
    payload: dict[str, Any] | None = None,
    event_id: str | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "event_id": event_id or str(uuid.uuid4()),
        "run_id": run_id,
        "machine_id": machine_id,
        "seq": seq,
        "type": event_type,
        "occurred_at": (at or datetime.now(UTC)).isoformat(),
        "payload": payload or {},
        "future_field": "ignored",
    }


def post_events(
    harness: Harness,
    machine: dict[str, Any],
    run_id: str,
    events: list[dict[str, Any]],
) -> httpx.Response:
    return harness.client.post(
        f"/v1/runs/{run_id}/events:batch",
        headers=auth(machine["credential"]),
        json={"events": events},
    )


def test_healthz_reports_data_region(harness: Harness) -> None:
    response = harness.client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "region": "global"}


def test_anonymous_bootstrap_cannot_rotate_existing_device_credential(
    harness: Harness,
) -> None:
    first = harness.bootstrap("installation-replay-protected")

    replay = harness.client.post(
        "/v1/devices/bootstrap",
        json={"installation_id": "installation-replay-protected"},
    )

    assert replay.status_code == 409
    assert replay.json()["detail"]["code"] == "installation_already_registered"
    assert harness.client.get("/v1/machines", headers=auth(first["credential"])).status_code == 200


def test_pairing_create_poll_claim_exchange_and_replay(harness: Harness) -> None:
    device = harness.bootstrap()
    created = harness.client.post(
        "/v1/pairing-sessions",
        json={"display_name": "MacBook", "platform": "darwin"},
    )
    assert created.status_code == 201
    pairing = created.json()
    assert len(pairing["short_code"]) == 6

    poll = harness.client.get(
        f"/v1/pairing-sessions/{pairing['pairing_session_id']}",
        headers=auth(pairing["exchange_secret"]),
    )
    assert poll.json()["status"] == "pending"
    claim = harness.client.post(
        f"/v1/pairing-sessions/{pairing['pairing_session_id']}/claim",
        headers=auth(device["credential"]),
        json={"challenge": pairing["challenge"]},
    )
    assert claim.status_code == 200
    assert (
        harness.client.post(
            f"/v1/pairing-sessions/{pairing['pairing_session_id']}/claim",
            headers=auth(device["credential"]),
            json={"challenge": pairing["challenge"]},
        ).status_code
        == 409
    )
    exchange_body = {"exchange_secret": pairing["exchange_secret"]}
    exchange = harness.client.post(
        f"/v1/pairing-sessions/{pairing['pairing_session_id']}/exchange",
        json=exchange_body,
    )
    assert exchange.status_code == 200
    assert exchange.json()["credential"].startswith("rbm_")
    assert (
        harness.client.post(
            f"/v1/pairing-sessions/{pairing['pairing_session_id']}/exchange",
            json=exchange_body,
        ).status_code
        == 409
    )

    with harness.session_factory() as session:
        row = session.get(PairingSession, pairing["pairing_session_id"])
        assert row is not None
        assert pairing["exchange_secret"] not in row.exchange_secret_hash


def test_pairing_expiry(harness: Harness) -> None:
    device = harness.bootstrap()
    created = harness.client.post(
        "/v1/pairing-sessions", json={"display_name": "Expired Mac"}
    ).json()
    with harness.session_factory() as session:
        pairing = session.get(PairingSession, created["pairing_session_id"])
        assert pairing is not None
        pairing.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        session.commit()
    response = harness.client.post(
        f"/v1/pairing-sessions/{created['pairing_session_id']}/claim",
        headers=auth(device["credential"]),
        json={"challenge": created["challenge"]},
    )
    assert response.status_code == 410


def test_run_upsert_refreshes_machine_cli_version_and_last_seen(harness: Harness) -> None:
    device, machine = harness.pair()
    with harness.session_factory() as session:
        stored = session.get(Machine, machine["machine_id"])
        assert stored is not None
        assert stored.cli_version == "0.1"
        previous_last_seen = stored.last_seen_at

    run_id = str(uuid.uuid4())
    response = harness.client.put(
        f"/v1/runs/{run_id}",
        headers=auth(machine["credential"]),
        json={
            "machine_id": machine["machine_id"],
            "title": "Version refresh",
            "source": "cli",
            "cli_version": "0.1.2",
        },
    )
    assert response.status_code == 200, response.text
    with harness.session_factory() as session:
        stored = session.get(Machine, machine["machine_id"])
        assert stored is not None
        assert stored.cli_version == "0.1.2"
        assert stored.last_seen_at >= previous_last_seen

    listed = harness.client.get("/v1/machines", headers=auth(device["credential"]))
    assert listed.status_code == 200
    assert listed.json()[0]["cli_version"] == "0.1.2"


def test_machine_can_update_only_its_own_canonical_name(harness: Harness) -> None:
    device, machine = harness.pair()
    updated = harness.client.patch(
        f"/v1/machines/{machine['machine_id']}",
        headers=auth(machine["credential"]),
        json={"display_name": "  Build Mac  "},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["display_name"] == "Build Mac"

    forbidden_device = harness.client.patch(
        f"/v1/machines/{machine['machine_id']}",
        headers=auth(device["credential"]),
        json={"display_name": "Phone Override"},
    )
    assert forbidden_device.status_code == 403
    forbidden_other = harness.client.patch(
        "/v1/machines/machine_other",
        headers=auth(machine["credential"]),
        json={"display_name": "Other Override"},
    )
    assert forbidden_other.status_code == 403

    listed = harness.client.get("/v1/machines", headers=auth(device["credential"]))
    assert listed.status_code == 200
    assert listed.json()[0]["display_name"] == "Build Mac"


def test_run_creation_and_confirmed_update_times_are_machine_event_times(
    harness: Harness,
) -> None:
    _device, machine = harness.pair()
    run_id = str(uuid.uuid4())
    harness.register_run(machine, run_id)
    created_at = datetime(2026, 7, 29, 8, 0, tzinfo=UTC)
    heartbeat_at = created_at + timedelta(seconds=15)
    regressed_at = created_at + timedelta(seconds=10)

    response = post_events(
        harness,
        machine,
        run_id,
        [
            event(run_id, machine["machine_id"], 1, "run.created", at=created_at),
            event(run_id, machine["machine_id"], 2, "run.started", at=created_at),
            event(run_id, machine["machine_id"], 3, "run.heartbeat", at=heartbeat_at),
            event(run_id, machine["machine_id"], 4, "run.message", at=regressed_at),
        ],
    )
    assert response.status_code == 200, response.text
    snapshot = response.json()["snapshot"]
    assert datetime.fromisoformat(snapshot["created_at"].replace("Z", "+00:00")) == created_at
    assert datetime.fromisoformat(snapshot["updated_at"].replace("Z", "+00:00")) == heartbeat_at


def test_scope_boundaries_and_encrypted_tokens(harness: Harness) -> None:
    device, machine = harness.pair()
    run_id = str(uuid.uuid4())
    machine_write = harness.client.put(
        f"/v1/runs/{run_id}",
        headers=auth(device["credential"]),
        json={"machine_id": machine["machine_id"], "title": "Forbidden"},
    )
    assert machine_write.status_code == 403
    machine_read = harness.client.get("/v1/runs", headers=auth(machine["credential"]))
    assert machine_read.status_code == 403

    token = "a" * 64
    response = harness.client.put(
        f"/v1/devices/{device['device_id']}/notification-token",
        headers=auth(device["credential"]),
        json={"token": token, "generation": 1},
    )
    assert response.status_code == 204
    with harness.session_factory() as session:
        stored = session.get(Device, device["device_id"])
        assert stored is not None
        assert stored.notification_token_encrypted is not None
        assert token not in stored.notification_token_encrypted


def test_notifications_are_enabled_by_default(harness: Harness) -> None:
    device = harness.bootstrap()
    with harness.session_factory() as session:
        stored = session.get(Device, device["device_id"])
        assert stored is not None
        assert stored.failure_notifications_enabled is True
        assert stored.success_notifications_enabled is True


def test_offline_terminal_batch_replay_is_ordered_and_idempotent(harness: Harness) -> None:
    device, machine = harness.pair()
    run_id = str(uuid.uuid4())
    harness.register_run(machine, run_id)
    started = datetime.now(UTC) - timedelta(seconds=30)
    events = [
        event(run_id, machine["machine_id"], 1, "run.created", at=started),
        event(
            run_id,
            machine["machine_id"],
            2,
            "run.started",
            at=started + timedelta(seconds=1),
        ),
        event(
            run_id,
            machine["machine_id"],
            3,
            "run.progress",
            at=started + timedelta(seconds=10),
            payload={
                "progress": {
                    "kind": "determinate",
                    "current": 50,
                    "total": 100,
                    "fraction": 0.5,
                    "source": "explicit",
                },
                "phase": "solve",
            },
        ),
        event(
            run_id,
            machine["machine_id"],
            4,
            "run.succeeded",
            at=started + timedelta(seconds=20),
            payload={
                "exit_code": 0,
                "message": "Complete",
                "safe_log_tail": ["safe line 1", "safe line 2"],
            },
        ),
    ]
    response = post_events(harness, machine, run_id, events)
    assert response.status_code == 200, response.text
    assert response.json()["snapshot"]["execution_status"] == "SUCCEEDED"
    assert response.json()["snapshot"]["last_seq"] == 4

    duplicate = post_events(harness, machine, run_id, events)
    assert duplicate.status_code == 200
    assert len(duplicate.json()["duplicates"]) == 4
    with harness.session_factory() as session:
        assert len(list(session.scalars(select(RunEvent)))) == 4

    read = harness.client.get(f"/v1/runs/{run_id}", headers=auth(device["credential"]))
    assert read.status_code == 200
    assert read.json()["run"]["sequence"] == 4
    assert read.json()["run"]["machine_name"] == "Test Mac"
    assert read.json()["run"]["safe_log_tail"] == ["safe line 1", "safe line 2"]
    assert [item["seq"] for item in read.json()["events"]] == [1, 2, 3, 4]


def test_out_of_order_duplicate_seq_and_terminal_protection(harness: Harness) -> None:
    _, machine = harness.pair()
    run_id = str(uuid.uuid4())
    harness.register_run(machine, run_id)
    first = event(run_id, machine["machine_id"], 1, "run.started")
    assert post_events(harness, machine, run_id, [first]).status_code == 200
    stale = event(run_id, machine["machine_id"], 1, "run.progress")
    assert post_events(harness, machine, run_id, [stale]).status_code == 409
    terminal = event(run_id, machine["machine_id"], 2, "run.failed")
    assert post_events(harness, machine, run_id, [terminal]).status_code == 200
    after = event(run_id, machine["machine_id"], 3, "run.progress")
    assert post_events(harness, machine, run_id, [after]).status_code == 409
    with harness.session_factory() as session:
        run = session.get(Run, run_id)
        assert run is not None
        assert run.execution_status == "FAILED"
        assert run.last_seq == 2
        assert session.scalar(select(RunEvent).where(RunEvent.seq == 3)) is None


def test_transactional_outbox_and_delayed_start(harness: Harness) -> None:
    device, machine = harness.pair()
    harness.client.put(
        f"/v1/devices/{device['device_id']}/push-to-start-token",
        headers=auth(device["credential"]),
        json={"token": "p" * 64},
    )
    run_id = str(uuid.uuid4())
    harness.register_run(machine, run_id)
    now = datetime.now(UTC)
    started = event(run_id, machine["machine_id"], 1, "run.started", at=now)
    assert post_events(harness, machine, run_id, [started]).status_code == 200
    with harness.session_factory() as session:
        outbox = session.scalar(select(PushOutbox))
        assert outbox is not None
        assert outbox.kind == "LIVE_START"
        assert outbox.status == "pending"
        assert outbox.priority == 10
        assert outbox.available_at.replace(tzinfo=UTC) >= now + timedelta(seconds=4)
        assert session.get(Run, run_id).last_seq == 1  # type: ignore[union-attr]


def test_short_failure_falls_back_without_live_token_and_short_success_is_silent(
    harness: Harness,
) -> None:
    device, machine = harness.pair()
    harness.client.put(
        f"/v1/devices/{device['device_id']}/notification-token",
        headers=auth(device["credential"]),
        json={"token": "n" * 64},
    )
    for terminal, expected_count in [("run.failed", 1), ("run.succeeded", 1)]:
        run_id = str(uuid.uuid4())
        harness.register_run(machine, run_id)
        now = datetime.now(UTC)
        response = post_events(
            harness,
            machine,
            run_id,
            [
                event(run_id, machine["machine_id"], 1, "run.started", at=now),
                event(
                    run_id,
                    machine["machine_id"],
                    2,
                    terminal,
                    at=now + timedelta(seconds=2),
                    payload={"message": "Finished"},
                ),
            ],
        )
        assert response.status_code == 200, response.text
        with harness.session_factory() as session:
            assert len(list(session.scalars(select(Notification)))) == expected_count


def test_long_success_fallback_is_enabled_by_default(harness: Harness) -> None:
    device, machine = harness.pair()
    harness.client.put(
        f"/v1/devices/{device['device_id']}/notification-token",
        headers=auth(device["credential"]),
        json={"token": "n" * 64},
    )
    run_id = str(uuid.uuid4())
    harness.register_run(machine, run_id)
    now = datetime.now(UTC) - timedelta(seconds=20)
    response = post_events(
        harness,
        machine,
        run_id,
        [
            event(run_id, machine["machine_id"], 1, "run.started", at=now),
            event(
                run_id,
                machine["machine_id"],
                2,
                "run.succeeded",
                at=now + timedelta(seconds=10),
            ),
        ],
    )
    assert response.status_code == 200
    with harness.session_factory() as session:
        notification = session.scalar(select(Notification))
        assert notification is not None and notification.level == "success"
        push = session.scalar(select(PushOutbox).where(PushOutbox.kind == "NOTIFICATION"))
        assert push is not None


def test_success_notification_can_be_disabled(harness: Harness) -> None:
    device, machine = harness.pair()
    harness.client.put(
        f"/v1/devices/{device['device_id']}/notification-token",
        headers=auth(device["credential"]),
        json={"token": "n" * 64},
    )
    harness.client.patch(
        "/v1/device-preferences",
        headers=auth(device["credential"]),
        json={"success_notifications_enabled": False},
    )
    response = harness.client.post(
        "/v1/notifications",
        headers=auth(machine["credential"]),
        json={"title": "Complete", "body": "Finished", "level": "success"},
    )
    assert response.status_code == 201
    with harness.session_factory() as session:
        assert session.scalar(select(Notification)) is not None
        assert session.scalar(select(PushOutbox).where(PushOutbox.kind == "NOTIFICATION")) is None


def test_notification_idempotency_and_read_api(harness: Harness) -> None:
    device, machine = harness.pair()
    token_response = harness.client.put(
        f"/v1/devices/{device['device_id']}/notification-token",
        headers=auth(device["credential"]),
        json={"token": "n" * 64},
    )
    assert token_response.status_code == 204
    body = {
        "title": "Build completed",
        "body": "Release build succeeded",
        "level": "success",
        "fields": [{"label": "Target", "value": "iOS"}],
        "safe_link": "https://example.com/build/1",
    }
    headers = {**auth(machine["credential"]), "Idempotency-Key": "build-1"}
    first = harness.client.post("/v1/notifications", headers=headers, json=body)
    second = harness.client.post("/v1/notifications", headers=headers, json=body)
    assert first.status_code == second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    read = harness.client.get("/v1/notifications", headers=auth(device["credential"]))
    assert read.json()[0]["fields"] == [{"label": "Target", "value": "iOS"}]
    with harness.session_factory() as session:
        pushes = list(session.scalars(select(PushOutbox).where(PushOutbox.kind == "NOTIFICATION")))
        assert len(pushes) == 1


def test_no_forbidden_or_websocket_routes(harness: Harness) -> None:
    application = cast(FastAPI, harness.client.app)
    paths = {route.path for route in application.routes if hasattr(route, "path")}
    forbidden_fragments = {
        "cancel",
        "retry",
        "input",
        "commands",
        "execute",
        "signal",
        "approve",
        "terminals",
    }
    assert not any(fragment in path for path in paths for fragment in forbidden_fragments)
    assert not any("websocket" in type(route).__name__.lower() for route in application.routes)
    assert harness.client.post(f"/v1/runs/{uuid.uuid4()}/cancel").status_code == 404
