from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.models import (
    AuditLog,
    LiveActivityBinding,
    Notification,
    PairingSession,
    PushAttempt,
    PushOutbox,
    Run,
    RunEvent,
)
from app.retention import cleanup_retention
from tests.conftest import Harness


def test_retention_is_bounded_idempotent_and_excludes_active_boundaries_and_live_runs(
    harness: Harness,
) -> None:
    device, machine = harness.pair()
    now = datetime(2026, 8, 7, 12, 0, tzinfo=UTC)
    old = now - timedelta(days=2)
    exact_day_cutoff = now - timedelta(days=1)
    exact_hour_cutoff = now - timedelta(hours=1)
    settings = replace(
        harness.settings,
        event_retention_hours=1,
        run_retention_days=1,
        notification_retention_days=1,
        push_attempt_retention_days=1,
        outbox_terminal_retention_days=1,
        pairing_retention_hours=24,
        audit_retention_days=1,
        safe_log_tail_retention_hours=1,
        retention_cleanup_batch_size=20,
    )
    run_ids = {
        "old": "20000000-0000-4000-8000-000000000001",
        "active": "20000000-0000-4000-8000-000000000002",
        "live": "20000000-0000-4000-8000-000000000003",
        "boundary": "20000000-0000-4000-8000-000000000004",
    }
    with harness.session_factory() as session:
        for name, run_id in run_ids.items():
            terminal = name != "active"
            session.add(
                Run(
                    id=run_id,
                    workspace_id=device["workspace_id"],
                    machine_id=machine["machine_id"],
                    title=name,
                    execution_status="SUCCEEDED" if terminal else "RUNNING",
                    created_at=old,
                    updated_at=old,
                    ended_at=(
                        exact_day_cutoff if name == "boundary" else old if terminal else None
                    ),
                    safe_log_tail=[name],
                )
            )
            session.add(
                RunEvent(
                    id=f"evt_{name}",
                    schema_version=1,
                    event_id=f"30000000-0000-4000-8000-00000000000{len(name)}",
                    run_id=run_id,
                    machine_id=machine["machine_id"],
                    seq=1,
                    type="run.heartbeat",
                    occurred_at=old,
                    received_at=exact_hour_cutoff if name == "boundary" else old,
                    payload={},
                )
            )
        session.flush()
        session.add(
            LiveActivityBinding(
                id="lab_retention_active",
                run_id=run_ids["live"],
                device_id=device["device_id"],
                activity_id="still-visible",
                state="active",
                started_at=old,
            )
        )
        session.add_all(
            [
                Notification(
                    id="ntf_retention_old",
                    workspace_id=device["workspace_id"],
                    title="old",
                    body="old",
                    level="info",
                    created_at=old,
                ),
                Notification(
                    id="ntf_retention_active",
                    workspace_id=device["workspace_id"],
                    run_id=run_ids["active"],
                    title="active",
                    body="active",
                    level="info",
                    created_at=old,
                ),
                Notification(
                    id="ntf_retention_boundary",
                    workspace_id=device["workspace_id"],
                    title="boundary",
                    body="boundary",
                    level="info",
                    created_at=exact_day_cutoff,
                ),
            ]
        )
        session.add_all(
            [
                PushOutbox(
                    id="out_retention_old",
                    kind="NOTIFICATION",
                    target_type="device",
                    target_id=device["device_id"],
                    desired_payload={"aps": {}},
                    status="sent",
                    coalesce_key="old",
                    created_at=old,
                    updated_at=old,
                ),
                PushOutbox(
                    id="out_retention_pending",
                    kind="NOTIFICATION",
                    target_type="device",
                    target_id=device["device_id"],
                    desired_payload={"aps": {}},
                    status="pending",
                    coalesce_key="pending",
                    created_at=old,
                    updated_at=old,
                ),
                PushOutbox(
                    id="out_retention_boundary",
                    kind="NOTIFICATION",
                    target_type="device",
                    target_id=device["device_id"],
                    desired_payload={"aps": {}},
                    status="sent",
                    coalesce_key="boundary",
                    created_at=exact_day_cutoff,
                    updated_at=exact_day_cutoff,
                ),
            ]
        )
        session.flush()
        session.add_all(
            [
                PushAttempt(
                    id="pat_retention_old",
                    outbox_id="out_retention_old",
                    attempted_at=old,
                    status_code=200,
                    request_payload={},
                    request_headers={},
                ),
                PushAttempt(
                    id="pat_retention_boundary",
                    outbox_id="out_retention_boundary",
                    attempted_at=exact_day_cutoff,
                    status_code=200,
                    request_payload={},
                    request_headers={},
                ),
            ]
        )
        session.add_all(
            [
                PairingSession(
                    id="pair_retention_old",
                    challenge="challenge-old",
                    short_code="000001",
                    exchange_secret_hash="hash-old",
                    requested_machine_metadata={},
                    expires_at=old,
                ),
                PairingSession(
                    id="pair_retention_boundary",
                    challenge="challenge-boundary",
                    short_code="000002",
                    exchange_secret_hash="hash-boundary",
                    requested_machine_metadata={},
                    expires_at=exact_day_cutoff,
                ),
            ]
        )
        session.add_all(
            [
                AuditLog(
                    id="aud_retention_old",
                    workspace_id=device["workspace_id"],
                    actor_type="device",
                    action="old",
                    created_at=old,
                ),
                AuditLog(
                    id="aud_retention_boundary",
                    workspace_id=device["workspace_id"],
                    actor_type="device",
                    action="boundary",
                    created_at=exact_day_cutoff,
                ),
            ]
        )
        session.commit()

        first = cleanup_retention(session, settings, now)
        session.commit()
        second = cleanup_retention(session, settings, now)
        session.commit()
        third = cleanup_retention(session, settings, now)
        session.commit()

        assert first["runs"] == 1
        assert first["notifications"] == 1
        assert first["events"] == 2  # old terminal Run events; active is excluded
        assert first["push_attempts"] == 1
        assert first["terminal_outbox"] == 1
        assert first["pairing_sessions"] == 1
        assert first["audit_logs"] == 1
        assert first["safe_log_tails"] == 4
        assert second["safe_log_tails"] == 0
        assert not any(third.values())
        assert session.get(Run, run_ids["old"]) is None
        assert session.get(Run, run_ids["active"]) is not None
        assert session.get(Run, run_ids["live"]) is not None
        assert session.get(Run, run_ids["boundary"]) is not None
        assert session.get(RunEvent, "evt_active") is not None
        assert session.get(RunEvent, "evt_boundary") is not None
        assert session.get(Notification, "ntf_retention_active") is not None
        assert session.get(Notification, "ntf_retention_boundary") is not None
        assert session.get(PushOutbox, "out_retention_pending") is not None
        assert session.get(PushOutbox, "out_retention_boundary") is not None
        assert session.get(PushAttempt, "pat_retention_boundary") is not None
        assert session.get(PairingSession, "pair_retention_boundary") is not None
        assert session.get(AuditLog, "aud_retention_boundary") is not None


def test_retention_batch_limit_requires_multiple_safe_passes(harness: Harness) -> None:
    device, _machine = harness.pair()
    now = datetime(2026, 8, 7, 12, 0, tzinfo=UTC)
    settings = replace(
        harness.settings,
        notification_retention_days=1,
        retention_cleanup_batch_size=1,
    )
    with harness.session_factory() as session:
        for index in range(2):
            session.add(
                Notification(
                    id=f"ntf_batch_{index}",
                    workspace_id=device["workspace_id"],
                    title="old",
                    body="old",
                    level="info",
                    created_at=now - timedelta(days=2),
                )
            )
        session.commit()

        first = cleanup_retention(session, settings, now)
        session.commit()
        second = cleanup_retention(session, settings, now)
        session.commit()
        third = cleanup_retention(session, settings, now)
        session.commit()

        assert first["notifications"] == 1
        assert second["notifications"] == 1
        assert third["notifications"] == 0
        assert (
            list(session.scalars(select(Notification).where(Notification.id.like("ntf_batch_%"))))
            == []
        )
