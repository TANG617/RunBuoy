from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import Select, delete, null, or_, select, update
from sqlalchemy.orm import Session

from .abuse import cleanup_abuse_state
from .config import Settings
from .models import (
    AuditLog,
    LiveActivityBinding,
    Notification,
    PairingSession,
    PushAttempt,
    PushOutbox,
    Run,
    RunEvent,
    WorkspaceDeletionChallenge,
    utcnow,
)
from .sync import bump_workspace_revision

TERMINAL_RUN_STATUSES = frozenset({"SUCCEEDED", "FAILED", "CANCELLED", "LOST"})
ACTIVE_LIVE_ACTIVITY_STATES = frozenset({"active", "stale"})
TERMINAL_OUTBOX_STATUSES = frozenset({"sent", "cancelled", "failed", "expired", "suppressed"})


def _limited_ids(session: Session, statement: Select[Any], batch_size: int) -> list[str]:
    return list(session.scalars(statement.limit(batch_size)))


def _delete_ids(session: Session, model: type[Any], ids: list[str]) -> int:
    if not ids:
        return 0
    result = session.execute(delete(model).where(model.id.in_(ids)))
    return int(result.rowcount or 0)  # type: ignore[attr-defined]


def cleanup_retention(
    session: Session,
    settings: Settings,
    now: datetime | None = None,
) -> dict[str, int]:
    """Delete one bounded, idempotent batch from each retention class.

    The caller owns the transaction. Active Runs and Runs with a deliverable Live
    Activity binding are never deleted. Exact cutoff timestamps are retained so
    an item becomes eligible only after it is strictly older than its policy.
    """

    current = now or utcnow()
    batch_size = settings.retention_cleanup_batch_size
    active_run_ids = select(Run.id).where(~Run.execution_status.in_(TERMINAL_RUN_STATUSES))

    notification_cutoff = current - timedelta(days=settings.notification_retention_days)
    notification_ids = _limited_ids(
        session,
        select(Notification.id)
        .where(
            or_(
                Notification.expires_at <= current,
                Notification.created_at < notification_cutoff,
            ),
            or_(Notification.run_id.is_(None), ~Notification.run_id.in_(active_run_ids)),
        )
        .order_by(Notification.created_at, Notification.id),
        batch_size,
    )
    changed_workspace_ids = set(
        session.scalars(
            select(Notification.workspace_id).where(Notification.id.in_(notification_ids))
        )
    )
    expired_notifications = _delete_ids(session, Notification, notification_ids)

    event_cutoff = current - timedelta(hours=settings.event_retention_hours)
    event_ids = _limited_ids(
        session,
        select(RunEvent.id)
        .join(Run, Run.id == RunEvent.run_id)
        .where(
            Run.execution_status.in_(TERMINAL_RUN_STATUSES),
            RunEvent.received_at < event_cutoff,
        )
        .order_by(RunEvent.received_at, RunEvent.id),
        batch_size,
    )
    if event_ids:
        changed_workspace_ids.update(
            session.scalars(
                select(Run.workspace_id)
                .join(RunEvent, RunEvent.run_id == Run.id)
                .where(RunEvent.id.in_(event_ids))
            )
        )
    old_events = _delete_ids(session, RunEvent, event_ids)

    safe_tail_cutoff = current - timedelta(hours=settings.safe_log_tail_retention_hours)
    tail_run_ids = _limited_ids(
        session,
        select(Run.id)
        .where(Run.updated_at < safe_tail_cutoff, Run.safe_log_tail.is_not(None))
        .order_by(Run.updated_at, Run.id),
        batch_size,
    )
    if tail_run_ids:
        changed_workspace_ids.update(
            session.scalars(select(Run.workspace_id).where(Run.id.in_(tail_run_ids)))
        )
    cleared_tails = 0
    if tail_run_ids:
        result = session.execute(
            update(Run).where(Run.id.in_(tail_run_ids)).values(safe_log_tail=null())
        )
        cleared_tails = int(result.rowcount or 0)  # type: ignore[attr-defined]

    pending_activity_cutoff = current - timedelta(
        seconds=settings.live_activity_pending_ttl_seconds
    )
    pending_binding_ids = _limited_ids(
        session,
        select(LiveActivityBinding.id)
        .where(
            LiveActivityBinding.activity_id.like("pending:%"),
            LiveActivityBinding.state == "active",
            LiveActivityBinding.started_at < pending_activity_cutoff,
        )
        .order_by(LiveActivityBinding.started_at, LiveActivityBinding.id),
        batch_size,
    )
    expired_pending_activities = 0
    if pending_binding_ids:
        result = session.execute(
            update(LiveActivityBinding)
            .where(LiveActivityBinding.id.in_(pending_binding_ids))
            .values(state="expired", ended_at=current, invalidated_at=current)
        )
        expired_pending_activities = int(result.rowcount or 0)  # type: ignore[attr-defined]

    attempt_cutoff = current - timedelta(days=settings.push_attempt_retention_days)
    attempt_ids = _limited_ids(
        session,
        select(PushAttempt.id)
        .where(PushAttempt.attempted_at < attempt_cutoff)
        .order_by(PushAttempt.attempted_at, PushAttempt.id),
        batch_size,
    )
    old_push_attempts = _delete_ids(session, PushAttempt, attempt_ids)

    outbox_cutoff = current - timedelta(days=settings.outbox_terminal_retention_days)
    outbox_ids = _limited_ids(
        session,
        select(PushOutbox.id)
        .where(
            PushOutbox.status.in_(TERMINAL_OUTBOX_STATUSES),
            PushOutbox.updated_at < outbox_cutoff,
        )
        .order_by(PushOutbox.updated_at, PushOutbox.id),
        batch_size,
    )
    if outbox_ids:
        session.execute(delete(PushAttempt).where(PushAttempt.outbox_id.in_(outbox_ids)))
    old_terminal_outbox = _delete_ids(session, PushOutbox, outbox_ids)

    pairing_cutoff = current - timedelta(hours=settings.pairing_retention_hours)
    pairing_ids = _limited_ids(
        session,
        select(PairingSession.id)
        .where(PairingSession.expires_at < pairing_cutoff)
        .order_by(PairingSession.expires_at, PairingSession.id),
        batch_size,
    )
    old_pairing_sessions = _delete_ids(session, PairingSession, pairing_ids)

    audit_cutoff = current - timedelta(days=settings.audit_retention_days)
    audit_ids = _limited_ids(
        session,
        select(AuditLog.id)
        .where(AuditLog.created_at < audit_cutoff)
        .order_by(AuditLog.created_at, AuditLog.id),
        batch_size,
    )
    old_audit_logs = _delete_ids(session, AuditLog, audit_ids)

    challenge_ids = _limited_ids(
        session,
        select(WorkspaceDeletionChallenge.id)
        .where(WorkspaceDeletionChallenge.expires_at <= current)
        .order_by(
            WorkspaceDeletionChallenge.expires_at,
            WorkspaceDeletionChallenge.id,
        ),
        batch_size,
    )
    expired_deletion_challenges = _delete_ids(session, WorkspaceDeletionChallenge, challenge_ids)

    run_cutoff = current - timedelta(days=settings.run_retention_days)
    active_binding_run_ids = select(LiveActivityBinding.run_id).where(
        LiveActivityBinding.state.in_(ACTIVE_LIVE_ACTIVITY_STATES),
        LiveActivityBinding.invalidated_at.is_(None),
    )
    old_run_ids = _limited_ids(
        session,
        select(Run.id)
        .where(
            Run.execution_status.in_(TERMINAL_RUN_STATUSES),
            Run.ended_at.is_not(None),
            Run.ended_at < run_cutoff,
            ~Run.id.in_(active_binding_run_ids),
        )
        .order_by(Run.ended_at, Run.id),
        batch_size,
    )
    if old_run_ids:
        changed_workspace_ids.update(
            session.scalars(select(Run.workspace_id).where(Run.id.in_(old_run_ids)))
        )
    old_runs = 0
    if old_run_ids:
        run_outbox_ids = list(
            session.scalars(select(PushOutbox.id).where(PushOutbox.run_id.in_(old_run_ids)))
        )
        if run_outbox_ids:
            session.execute(delete(PushAttempt).where(PushAttempt.outbox_id.in_(run_outbox_ids)))
            session.execute(delete(PushOutbox).where(PushOutbox.id.in_(run_outbox_ids)))
        session.execute(delete(RunEvent).where(RunEvent.run_id.in_(old_run_ids)))
        session.execute(
            delete(LiveActivityBinding).where(LiveActivityBinding.run_id.in_(old_run_ids))
        )
        session.execute(
            update(Notification).where(Notification.run_id.in_(old_run_ids)).values(run_id=None)
        )
        old_runs = _delete_ids(session, Run, old_run_ids)

    abuse_cleanup = cleanup_abuse_state(session, settings, now=current)

    for workspace_id in sorted(changed_workspace_ids):
        bump_workspace_revision(session, workspace_id)

    return {
        "notifications": expired_notifications,
        "events": old_events,
        "safe_log_tails": cleared_tails,
        "pending_live_activities": expired_pending_activities,
        "push_attempts": old_push_attempts,
        "terminal_outbox": old_terminal_outbox,
        "pairing_sessions": old_pairing_sessions,
        "audit_logs": old_audit_logs,
        "deletion_challenges": expired_deletion_challenges,
        "runs": old_runs,
        **abuse_cleanup,
    }
