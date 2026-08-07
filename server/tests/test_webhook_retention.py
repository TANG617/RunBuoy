from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select

from app.models import LiveActivityBinding, Notification, Run, RunEvent, Webhook
from app.schemas import RunEvent as RunEventInput
from app.services import cleanup_retention, ingest_events
from tests.conftest import Harness
from tests.test_api import auth


def test_webhook_notification_run_progress_end_and_revocation(harness: Harness) -> None:
    device, machine = harness.pair()
    created = harness.client.post(
        "/v1/webhooks",
        headers=auth(machine["credential"]),
        json={"name": "CI"},
    )
    assert created.status_code == 201
    hook = created.json()
    hook_headers = auth(hook["secret"])
    run_body = {
        "machine_id": machine["machine_id"],
        "title": "Webhook build",
        "source": "github",
    }
    run = harness.client.put(
        f"/v1/hooks/{hook['hook_id']}/runs/build-42",
        headers=hook_headers,
        json=run_body,
    )
    assert run.status_code == 200
    run_id = run.json()["id"]
    for index, event_type in enumerate(["run.started", "run.progress", "run.succeeded"], start=1):
        body: dict[str, Any] = {"type": event_type}
        if event_type == "run.progress":
            body["progress"] = {
                "kind": "determinate",
                "current": 5,
                "total": 10,
                "fraction": 0.5,
            }
        response = harness.client.post(
            f"/v1/hooks/{hook['hook_id']}/runs/build-42/events",
            headers={**hook_headers, "Idempotency-Key": f"event-{index}"},
            json=body,
        )
        assert response.status_code == 202, response.text
    notification = harness.client.post(
        f"/v1/hooks/{hook['hook_id']}/notifications",
        headers={**hook_headers, "Idempotency-Key": "notice-1"},
        json={"title": "CI", "body": "Done", "level": "success"},
    )
    assert notification.status_code == 201
    read = harness.client.get(f"/v1/runs/{run_id}", headers=auth(device["credential"]))
    assert read.json()["run"]["execution_status"] == "SUCCEEDED"
    assert len(read.json()["events"]) == 3

    revoked = harness.client.delete(
        f"/v1/webhooks/{hook['hook_id']}",
        headers=auth(machine["credential"]),
    )
    assert revoked.status_code == 204
    assert (
        harness.client.post(
            f"/v1/hooks/{hook['hook_id']}/notifications",
            headers=hook_headers,
            json={"title": "No", "body": "Rejected"},
        ).status_code
        == 401
    )
    with harness.session_factory() as session:
        stored = session.get(Webhook, hook["hook_id"])
        assert stored is not None and stored.revoked_at is not None
        assert hook["secret"] not in stored.token_hash


def test_retention_cleanup(harness: Harness) -> None:
    device, machine = harness.pair()
    run_id = str(uuid.uuid4())
    harness.register_run(machine, run_id)
    old = datetime.now(UTC) - timedelta(hours=48)
    with harness.session_factory() as session:
        run = session.get(Run, run_id)
        assert run is not None
        events = [
            RunEventInput(
                schema_version=1,
                event_id=uuid.uuid4(),
                run_id=uuid.UUID(run_id),
                machine_id=machine["machine_id"],
                seq=1,
                type="run.failed",
                occurred_at=old,
                payload={},
            )
        ]
        ingest_events(session, harness.settings, run, events)
        run.safe_log_tail = ["expires"]
        session.flush()
        stored_event = session.scalar(select(RunEvent))
        assert stored_event is not None
        stored_event.received_at = old
        session.add(
            Notification(
                id="ntf_expired",
                workspace_id=machine["workspace_id"],
                machine_id=machine["machine_id"],
                title="Expired",
                body="Expired",
                level="info",
                expires_at=old,
            )
        )
        session.add(
            LiveActivityBinding(
                id="lab_expired_pending",
                run_id=run_id,
                device_id=device["device_id"],
                activity_id="pending:expired-start",
                state="active",
                started_at=old,
            )
        )
        session.commit()
        result = cleanup_retention(session, harness.settings)
        session.commit()
        expected = {
            "notifications": 1,
            "events": 1,
            "safe_log_tails": 1,
            "pending_live_activities": 1,
            "rate_limit_buckets": 0,
            "quota_locks": 0,
        }
        assert {key: result[key] for key in expected} == expected
        assert session.get(Run, run_id).safe_log_tail is None  # type: ignore[union-attr]
        binding = session.get(LiveActivityBinding, "lab_expired_pending")
        assert binding is not None and binding.state == "expired"
