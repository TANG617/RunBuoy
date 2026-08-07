from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from .abuse import enforce_notification_daily_quota
from .config import Settings
from .models import (
    Device,
    LiveActivityBinding,
    Machine,
    MachineDeviceSubscription,
    Notification,
    PushOutbox,
    Run,
    RunEvent,
    utcnow,
)
from .schemas import NotificationCreate
from .schemas import RunEvent as RunEventInput
from .security import new_id

TERMINAL_STATUSES = frozenset({"SUCCEEDED", "FAILED", "CANCELLED", "LOST"})
LIVE_ACTIVITY_DELIVERABLE_STATES = frozenset({"active", "stale"})
EVENT_STATUS = {
    "run.created": "CREATED",
    "run.starting": "STARTING",
    "run.started": "RUNNING",
    "run.succeeded": "SUCCEEDED",
    "run.failed": "FAILED",
    "run.cancelled": "CANCELLED",
    "run.lost": "LOST",
}
ALLOWED_TRANSITIONS = {
    "CREATED": frozenset({"CREATED", "STARTING", "RUNNING", *TERMINAL_STATUSES}),
    "STARTING": frozenset({"STARTING", "RUNNING", *TERMINAL_STATUSES}),
    "RUNNING": frozenset({"RUNNING", *TERMINAL_STATUSES}),
}


def aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def run_snapshot(run: Run) -> dict[str, Any]:
    return {
        "id": run.id,
        "workspace_id": run.workspace_id,
        "machine_id": run.machine_id,
        "title": run.title,
        "source": run.source,
        "execution_status": run.execution_status,
        "health_status": run.health_status,
        "attention_status": run.attention_status,
        "progress": run.progress,
        "phase": run.phase,
        "safe_message": run.safe_message,
        "created_at": run.created_at,
        "started_at": run.started_at,
        "updated_at": run.updated_at,
        "ended_at": run.ended_at,
        "exit_code": run.exit_code,
        "termination_reason": run.termination_reason,
        "last_seq": run.last_seq,
        "sequence": run.last_seq,
        "machine_name": run.machine.display_name,
        "safe_log_tail": run.safe_log_tail,
    }


def live_content_state(run: Run, *, machine_name: str | None = None) -> dict[str, Any]:
    progress = run.progress or {}
    content: dict[str, Any] = {
        "sequence": max(run.last_seq, 1),
        "executionStatus": run.execution_status,
        "healthStatus": run.health_status,
        "attentionStatus": run.attention_status,
        "progressKind": progress.get("kind", "indeterminate"),
        "progress": progress.get("fraction"),
        "current": progress.get("current"),
        "total": progress.get("total"),
        "phase": run.phase,
        "message": run.safe_message,
        "createdAt": aware(run.created_at).isoformat(),
        "startedAt": aware(run.started_at or run.updated_at).isoformat(),
        "updatedAt": aware(run.updated_at).isoformat(),
        "machineName": machine_name or run.machine_id,
        "estimatedEndAt": progress.get("estimated_end_at"),
        "exitCode": run.exit_code,
    }
    if run.ended_at is not None:
        content["endedAt"] = aware(run.ended_at).isoformat()
    return content


def live_payload(
    run: Run,
    kind: str,
    now: datetime | None = None,
    *,
    machine_name: str | None = None,
) -> dict[str, Any]:
    """Build ActivityKit push payloads from Apple's current documented keys.

    Source: https://developer.apple.com/documentation/activitykit/
    starting-and-updating-live-activities-with-activitykit-push-notifications
    The `timestamp`, `event`, and `content-state` keys are required for the
    corresponding ActivityKit event. `stale-date` is a Unix timestamp. A start
    also includes `attributes-type` and `attributes`. End payloads intentionally
    use ActivityKit's default dismissal behavior so final state can remain on
    the Lock Screen for up to four hours.
    """
    current = now or utcnow()
    aps: dict[str, Any] = {
        "timestamp": int(current.timestamp()),
        "event": {"LIVE_START": "start", "LIVE_UPDATE": "update", "LIVE_END": "end"}[kind],
        "content-state": live_content_state(run, machine_name=machine_name),
    }
    if kind != "LIVE_END":
        aps["stale-date"] = int((aware(run.updated_at) + timedelta(seconds=60)).timestamp())
    if kind == "LIVE_START":
        aps.update(
            {
                "attributes-type": "RunActivityAttributes",
                "input-push-token": 1,
                "attributes": {
                    "runID": run.id,
                    "title": run.title,
                    "machineName": machine_name or run.machine_id,
                    "schemaVersion": 1,
                },
                "alert": {
                    "title": run.title,
                    "body": run.safe_message or "Run is still in progress",
                },
            }
        )
    return {"aps": aps}


def normal_payload(notification: Notification) -> dict[str, Any]:
    alert: dict[str, str] = {"title": notification.title, "body": notification.body}
    if notification.subtitle:
        alert["subtitle"] = notification.subtitle
    payload: dict[str, Any] = {
        "aps": {"alert": alert},
        "runbuoy": {
            "notificationID": notification.id,
            "level": notification.level,
        },
    }
    if notification.run_id:
        payload["runbuoy"]["runID"] = notification.run_id
    return payload


def _priority(
    run: Run,
    kind: str,
    *,
    event_type: str | None = None,
    previous_progress: dict[str, Any] | None = None,
) -> int:
    if (
        kind in {"LIVE_START", "LIVE_END"}
        or run.attention_status in {"WARNING", "ACTION_REQUIRED"}
        or run.execution_status in {"FAILED", "LOST"}
        or event_type == "run.phase_changed"
    ):
        return 10
    if event_type == "run.progress":
        previous_fraction = (previous_progress or {}).get("fraction")
        current_fraction = (run.progress or {}).get("fraction")
        if not isinstance(previous_fraction, int | float):
            return 10
        if (
            isinstance(current_fraction, int | float)
            and abs(current_fraction - previous_fraction) >= 0.1
        ):
            return 10
    return 5


def _signal_outbox_worker(session: Session) -> None:
    """Wake PostgreSQL workers after commit; SQLite workers keep their poll fallback."""
    if session.get_bind().dialect.name == "postgresql":
        session.execute(
            text("SELECT pg_notify('runbuoy_push_outbox', '')"),
        )


def _coalesce_outbox(
    session: Session,
    *,
    kind: str,
    target_type: str,
    target_id: str,
    run_id: str | None,
    payload: dict[str, Any],
    priority: int,
    available_at: datetime,
    coalesce_key: str,
) -> PushOutbox:
    existing = session.scalar(
        select(PushOutbox).where(
            PushOutbox.coalesce_key == coalesce_key,
            PushOutbox.status == "pending",
        )
    )
    if existing is not None:
        existing.kind = kind
        existing.desired_payload = payload
        existing.priority = max(existing.priority, priority)
        existing.available_at = min(aware(existing.available_at), aware(available_at))
        existing.updated_at = utcnow()
        _signal_outbox_worker(session)
        return existing
    outbox = PushOutbox(
        id=new_id("out"),
        kind=kind,
        target_type=target_type,
        target_id=target_id,
        run_id=run_id,
        desired_payload=payload,
        priority=priority,
        available_at=available_at,
        status="pending",
        coalesce_key=coalesce_key,
    )
    session.add(outbox)
    _signal_outbox_worker(session)
    return outbox


def _subscribed_devices(session: Session, run: Run) -> list[Device]:
    return list(
        session.scalars(
            select(Device)
            .join(
                MachineDeviceSubscription,
                MachineDeviceSubscription.device_id == Device.id,
            )
            .where(
                MachineDeviceSubscription.machine_id == run.machine_id,
                Device.revoked_at.is_(None),
            )
        )
    )


def _schedule_notification_push(
    session: Session, notification: Notification, *, priority: int = 10
) -> None:
    devices_query = select(Device).where(
        Device.workspace_id == notification.workspace_id,
        Device.revoked_at.is_(None),
        Device.notification_token_encrypted.is_not(None),
    )
    if notification.machine_id is not None:
        devices_query = devices_query.join(
            MachineDeviceSubscription,
            MachineDeviceSubscription.device_id == Device.id,
        ).where(MachineDeviceSubscription.machine_id == notification.machine_id)
    devices = list(session.scalars(devices_query))
    for device in devices:
        if notification.level == "success" and not device.success_notifications_enabled:
            continue
        if notification.level == "error" and not device.failure_notifications_enabled:
            continue
        _coalesce_outbox(
            session,
            kind="NOTIFICATION",
            target_type="device",
            target_id=device.id,
            run_id=notification.run_id,
            payload=normal_payload(notification),
            priority=priority,
            available_at=utcnow(),
            coalesce_key=f"notification:{notification.id}:{device.id}",
        )


def create_notification(
    session: Session,
    settings: Settings,
    *,
    workspace_id: str,
    machine_id: str | None,
    body: NotificationCreate,
    dedupe_key: str | None,
) -> Notification:
    if dedupe_key is not None:
        existing = session.scalar(
            select(Notification).where(
                Notification.workspace_id == workspace_id,
                Notification.dedupe_key == dedupe_key,
            )
        )
        if existing is not None:
            return existing
    enforce_notification_daily_quota(
        session,
        settings,
        workspace_id=workspace_id,
    )
    notification = Notification(
        id=new_id("ntf"),
        workspace_id=workspace_id,
        machine_id=machine_id,
        run_id=body.run_id,
        title=body.title,
        subtitle=body.subtitle,
        body=body.body,
        level=body.level,
        fields=[item.model_dump() for item in body.fields],
        safe_link=str(body.safe_link) if body.safe_link is not None else None,
        dedupe_key=dedupe_key,
        expires_at=body.expires_at,
    )
    session.add(notification)
    session.flush()
    _schedule_notification_push(session, notification)
    return notification


def _create_fallback_notification(
    session: Session,
    settings: Settings,
    *,
    workspace_id: str,
    machine_id: str,
    body: NotificationCreate,
    dedupe_key: str,
) -> None:
    try:
        # An automatic fallback must never prevent the terminal Run projection
        # from converging. Roll back only notification accounting/materialization
        # when the Workspace has exhausted its daily notification quota.
        with session.begin_nested():
            create_notification(
                session,
                settings,
                workspace_id=workspace_id,
                machine_id=machine_id,
                body=body,
                dedupe_key=dedupe_key,
            )
    except HTTPException as exc:
        detail: dict[str, Any] = exc.detail if isinstance(exc.detail, dict) else {}
        if (
            exc.status_code != status.HTTP_429_TOO_MANY_REQUESTS
            or detail.get("resource") != "notifications"
        ):
            raise


def schedule_binding_end(
    session: Session,
    run: Run,
    binding: LiveActivityBinding,
) -> PushOutbox:
    machine_name = run.machine.display_name
    return _coalesce_outbox(
        session,
        kind="LIVE_END",
        target_type="activity",
        target_id=binding.id,
        run_id=run.id,
        payload=live_payload(run, "LIVE_END", machine_name=machine_name),
        priority=10,
        available_at=utcnow(),
        coalesce_key=f"live:{run.id}:{binding.device_id}",
    )


def schedule_binding_update(
    session: Session,
    run: Run,
    binding: LiveActivityBinding,
) -> PushOutbox:
    machine_name = run.machine.display_name
    return _coalesce_outbox(
        session,
        kind="LIVE_UPDATE",
        target_type="activity",
        target_id=binding.id,
        run_id=run.id,
        payload=live_payload(run, "LIVE_UPDATE", machine_name=machine_name),
        priority=_priority(run, "LIVE_UPDATE"),
        available_at=utcnow(),
        coalesce_key=f"live:{run.id}:{binding.device_id}",
    )


def schedule_run_pushes(
    session: Session,
    settings: Settings,
    run: Run,
    *,
    event_type: str,
    previous_progress: dict[str, Any] | None,
) -> None:
    now = utcnow()
    machine = session.get(Machine, run.machine_id)
    machine_name = machine.display_name if machine is not None else run.machine_id
    if event_type in {"run.started", "run.starting"}:
        for device in _subscribed_devices(session, run):
            if (
                run.live_activity_policy != "disabled"
                and device.live_activities_enabled
                and device.push_to_start_token_encrypted
            ):
                start_delay = (
                    0
                    if run.live_activity_policy == "immediate"
                    else settings.live_activity_start_delay_seconds
                )
                available = (run.started_at or now) + timedelta(seconds=start_delay)
                _coalesce_outbox(
                    session,
                    kind="LIVE_START",
                    target_type="device",
                    target_id=device.id,
                    run_id=run.id,
                    payload=live_payload(
                        run,
                        "LIVE_START",
                        now,
                        machine_name=machine_name,
                    ),
                    priority=_priority(run, "LIVE_START"),
                    available_at=available,
                    coalesce_key=f"live-start:{run.id}:{device.id}",
                )
        return

    pending_starts = list(
        session.scalars(
            select(PushOutbox).where(
                PushOutbox.run_id == run.id,
                PushOutbox.kind == "LIVE_START",
                PushOutbox.status == "pending",
            )
        )
    )
    for pending_start in pending_starts:
        pending_start.desired_payload = live_payload(
            run,
            "LIVE_START",
            now,
            machine_name=machine_name,
        )
        pending_start.priority = max(pending_start.priority, _priority(run, "LIVE_START"))
        pending_start.updated_at = now

    if run.execution_status in TERMINAL_STATUSES:
        for pending in pending_starts:
            pending.status = "cancelled"
            pending.updated_at = now

        duration = None
        if run.started_at and run.ended_at:
            duration = (aware(run.ended_at) - aware(run.started_at)).total_seconds()
        sent_start_exists = (
            session.scalar(
                select(PushOutbox.id).where(
                    PushOutbox.run_id == run.id,
                    PushOutbox.kind == "LIVE_START",
                    PushOutbox.status == "sent",
                )
            )
            is not None
        )
        should_fallback_failure = (
            run.execution_status in {"FAILED", "LOST"} and not sent_start_exists
        )
        if should_fallback_failure:
            body = NotificationCreate(
                title=run.title,
                body=run.safe_message or f"Run {run.execution_status.lower()}",
                level="error",
                run_id=run.id,
            )
            _create_fallback_notification(
                session,
                settings,
                workspace_id=run.workspace_id,
                machine_id=run.machine_id,
                body=body,
                dedupe_key=f"terminal-fallback:{run.id}",
            )
        should_fallback_success = (
            run.execution_status == "SUCCEEDED"
            and duration is not None
            and duration > 5
            and not sent_start_exists
        )
        if should_fallback_success:
            _create_fallback_notification(
                session,
                settings,
                workspace_id=run.workspace_id,
                machine_id=run.machine_id,
                body=NotificationCreate(
                    title=run.title,
                    body=run.safe_message or "Run succeeded",
                    level="success",
                    run_id=run.id,
                ),
                dedupe_key=f"terminal-fallback:{run.id}",
            )
    bindings = list(
        session.scalars(
            select(LiveActivityBinding).where(
                LiveActivityBinding.run_id == run.id,
                LiveActivityBinding.state.in_(LIVE_ACTIVITY_DELIVERABLE_STATES),
                LiveActivityBinding.invalidated_at.is_(None),
                LiveActivityBinding.update_push_token_encrypted.is_not(None),
            )
        )
    )
    kind = "LIVE_END" if run.execution_status in TERMINAL_STATUSES else "LIVE_UPDATE"
    for binding in bindings:
        available_at = now
        if kind == "LIVE_UPDATE" and event_type == "run.progress":
            delivery_device = session.get(Device, binding.device_id)
            update_interval = settings.live_activity_update_interval_seconds
            if (
                delivery_device is not None
                and not delivery_device.frequent_live_activity_updates_enabled
            ):
                update_interval = max(update_interval, 15)
            coalesce_key = f"live:{run.id}:{binding.device_id}"
            latest_sent = session.scalar(
                select(PushOutbox)
                .where(
                    PushOutbox.coalesce_key == coalesce_key,
                    PushOutbox.status == "sent",
                )
                .order_by(PushOutbox.updated_at.desc())
                .limit(1)
            )
            if latest_sent is not None:
                available_at = max(
                    now,
                    aware(latest_sent.updated_at) + timedelta(seconds=update_interval),
                )
            previous_fraction = (previous_progress or {}).get("fraction")
            current_fraction = (run.progress or {}).get("fraction")
            if (
                isinstance(previous_fraction, int | float)
                and isinstance(current_fraction, int | float)
                and abs(current_fraction - previous_fraction) < 0.01
            ):
                available_at = now + timedelta(seconds=update_interval)
        _coalesce_outbox(
            session,
            kind=kind,
            target_type="activity",
            target_id=binding.id,
            run_id=run.id,
            payload=live_payload(run, kind, now, machine_name=machine_name),
            priority=_priority(
                run,
                kind,
                event_type=event_type,
                previous_progress=previous_progress,
            ),
            available_at=available_at,
            coalesce_key=f"live:{run.id}:{binding.device_id}",
        )


def _validate_transition(run: Run, event: RunEventInput) -> None:
    next_status = EVENT_STATUS.get(event.type)
    if run.execution_status in TERMINAL_STATUSES:
        raise HTTPException(status.HTTP_409_CONFLICT, "terminal run state is immutable")
    if next_status is not None and next_status not in ALLOWED_TRANSITIONS[run.execution_status]:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"illegal transition: {run.execution_status} -> {next_status}",
        )


def ingest_events(
    session: Session,
    settings: Settings,
    run: Run,
    events: list[RunEventInput],
) -> dict[str, Any]:
    inserted: list[str] = []
    duplicates: list[str] = []
    for event in sorted(events, key=lambda item: item.seq):
        existing_by_id = session.scalar(
            select(RunEvent).where(RunEvent.event_id == str(event.event_id))
        )
        if existing_by_id is not None:
            if (
                existing_by_id.run_id == run.id
                and existing_by_id.seq == event.seq
                and existing_by_id.type == event.type
            ):
                duplicates.append(str(event.event_id))
                continue
            raise HTTPException(status.HTTP_409_CONFLICT, "event_id replay mismatch")
        existing_by_seq = session.scalar(
            select(RunEvent).where(RunEvent.run_id == run.id, RunEvent.seq == event.seq)
        )
        if existing_by_seq is not None:
            raise HTTPException(status.HTTP_409_CONFLICT, "sequence already has another event")
        if event.seq <= run.last_seq:
            raise HTTPException(status.HTTP_409_CONFLICT, "out-of-order event")
        if str(event.run_id) != run.id or event.machine_id != run.machine_id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "event ownership mismatch")

        _validate_transition(run, event)
        previous_progress = run.progress
        record = RunEvent(
            id=new_id("evt"),
            schema_version=event.schema_version,
            event_id=str(event.event_id),
            run_id=run.id,
            machine_id=run.machine_id,
            seq=event.seq,
            type=event.type,
            occurred_at=event.occurred_at,
            payload=event.payload,
        )
        session.add(record)

        if run.last_seq == 0:
            run.updated_at = event.occurred_at
        else:
            run.updated_at = max(aware(run.updated_at), event.occurred_at)
        run.last_seq = event.seq
        if event.type == "run.created":
            run.created_at = event.occurred_at
        next_status = EVENT_STATUS.get(event.type)
        if next_status is not None:
            run.execution_status = next_status
        if event.type in {"run.started", "run.starting"} and run.started_at is None:
            run.started_at = event.occurred_at
        if next_status in TERMINAL_STATUSES:
            run.ended_at = event.occurred_at
        if "progress" in event.payload:
            run.progress = event.payload["progress"]
        if "phase" in event.payload:
            run.phase = event.payload["phase"]
        if "message" in event.payload:
            run.safe_message = event.payload["message"]
        if "attention_status" in event.payload and event.payload["attention_status"] is not None:
            run.attention_status = event.payload["attention_status"]
        if "exit_code" in event.payload:
            run.exit_code = event.payload["exit_code"]
        if "termination_reason" in event.payload:
            run.termination_reason = event.payload["termination_reason"]
        if "safe_log_tail" in event.payload:
            run.safe_log_tail = event.payload["safe_log_tail"]

        schedule_run_pushes(
            session,
            settings,
            run,
            event_type=event.type,
            previous_progress=previous_progress,
        )
        inserted.append(str(event.event_id))
    session.flush()
    return {
        "inserted": inserted,
        "duplicates": duplicates,
        "last_seq": run.last_seq,
        "snapshot": run_snapshot(run),
    }


def cleanup_retention(
    session: Session,
    settings: Settings,
    now: datetime | None = None,
) -> dict[str, int]:
    from .retention import cleanup_retention as cleanup

    return cleanup(session, settings, now)


def deterministic_webhook_run_id(webhook_id: str, external_run_id: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"runbuoy:{webhook_id}:{external_run_id}"))
