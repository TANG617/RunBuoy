from __future__ import annotations

import hmac
from datetime import timedelta
from typing import Any, NoReturn, cast

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, or_, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from .abuse import anonymized_key
from .auth import Principal, authenticate
from .config import Settings
from .database import get_session
from .models import (
    AuditLog,
    Device,
    DeviceCredential,
    LiveActivityBinding,
    Machine,
    MachineCredential,
    MachineDeviceSubscription,
    Notification,
    PairingSession,
    PushAttempt,
    PushOutbox,
    QuotaLock,
    RateLimitBucket,
    Run,
    RunEvent,
    Webhook,
    Workspace,
    WorkspaceDeletionChallenge,
    utcnow,
)
from .security import is_expired, new_bearer_token, new_id, token_hash
from .sync import bump_workspace_revision

router = APIRouter(prefix="/v1")


class DeletionChallengeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirmation: str = Field(min_length=1, max_length=32)


class WorkspaceDeleteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    challenge: str = Field(min_length=16, max_length=256)


def _settings(request: Request) -> Settings:
    return request.app.state.settings


def _error(http_status: int, code: str, message: str) -> NoReturn:
    raise HTTPException(
        http_status,
        detail={"code": code, "message": message},
    )


def _require_device(principal: Principal) -> None:
    if principal.kind != "device":
        _error(
            status.HTTP_403_FORBIDDEN,
            "device_credential_required",
            "device credential required",
        )


def _require_machine(principal: Principal) -> None:
    if principal.kind != "machine":
        _error(
            status.HTTP_403_FORBIDDEN,
            "machine_credential_required",
            "machine credential required",
        )


def _audit(
    session: Session,
    principal: Principal,
    action: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    session.add(
        AuditLog(
            id=new_id("aud"),
            workspace_id=principal.workspace_id,
            actor_type=principal.kind,
            actor_id=principal.subject_id,
            action=action,
            metadata_json=metadata or {},
        )
    )


def _machine_run_ids(machine_id: str) -> Any:
    return select(Run.id).where(Run.machine_id == machine_id)


def _device_binding_ids(session: Session, device_id: str, run_ids: Any) -> list[str]:
    return list(
        session.scalars(
            select(LiveActivityBinding.id).where(
                LiveActivityBinding.device_id == device_id,
                LiveActivityBinding.run_id.in_(run_ids),
            )
        )
    )


def _machine_notification_keys(
    session: Session,
    machine_id: str,
    device_ids: list[str],
) -> list[str]:
    if not device_ids:
        return []
    notification_ids = list(
        session.scalars(select(Notification.id).where(Notification.machine_id == machine_id))
    )
    return [
        f"notification:{notification_id}:{device_id}"
        for notification_id in notification_ids
        for device_id in device_ids
    ]


def _cancel_pending_pushes(
    session: Session,
    *,
    machine_id: str,
    device_ids: list[str],
    reason: str,
) -> int:
    if not device_ids:
        return 0
    now = utcnow()
    run_ids = _machine_run_ids(machine_id)
    binding_ids: list[str] = []
    for device_id in device_ids:
        binding_ids.extend(_device_binding_ids(session, device_id, run_ids))
    notification_keys = _machine_notification_keys(session, machine_id, device_ids)
    target_filters: list[ColumnElement[bool]] = [
        (PushOutbox.target_type == "device") & PushOutbox.target_id.in_(device_ids),
    ]
    if binding_ids:
        target_filters.append(
            (PushOutbox.target_type == "activity") & PushOutbox.target_id.in_(binding_ids)
        )
    filters: list[ColumnElement[bool]] = [(PushOutbox.run_id.in_(run_ids)) & or_(*target_filters)]
    if notification_keys:
        filters.append(PushOutbox.coalesce_key.in_(notification_keys))
    result = cast(
        CursorResult[Any],
        session.execute(
            update(PushOutbox)
            .where(PushOutbox.status == "pending", or_(*filters))
            .values(status="cancelled", last_error=reason, updated_at=now)
        ),
    )
    return int(result.rowcount or 0)


def stop_receiving_subscription(
    session: Session,
    principal: Principal,
    subscription_id: str,
) -> None:
    _require_device(principal)
    subscription = session.get(MachineDeviceSubscription, subscription_id)
    if (
        subscription is None
        or subscription.device_id != principal.subject_id
        or session.get(Machine, subscription.machine_id) is None
    ):
        _error(status.HTTP_404_NOT_FOUND, "subscription_not_found", "subscription not found")
    machine = session.get(Machine, subscription.machine_id)
    if machine is None or machine.workspace_id != principal.workspace_id:
        _error(status.HTTP_404_NOT_FOUND, "subscription_not_found", "subscription not found")
    cancelled = _cancel_pending_pushes(
        session,
        machine_id=subscription.machine_id,
        device_ids=[principal.subject_id],
        reason="device stopped receiving from machine",
    )
    session.delete(subscription)
    _audit(
        session,
        principal,
        "subscription.stop_receiving",
        {"machine_id": machine.id, "cancelled_pushes": cancelled},
    )


def _revoke_machine(
    session: Session,
    principal: Principal,
    machine: Machine,
) -> None:
    now = utcnow()
    device_ids = list(
        session.scalars(
            select(MachineDeviceSubscription.device_id).where(
                MachineDeviceSubscription.machine_id == machine.id
            )
        )
    )
    cancelled = _cancel_pending_pushes(
        session,
        machine_id=machine.id,
        device_ids=device_ids,
        reason="machine credential revoked",
    )
    credential_count = cast(
        CursorResult[Any],
        session.execute(
            update(MachineCredential)
            .where(
                MachineCredential.machine_id == machine.id,
                MachineCredential.revoked_at.is_(None),
            )
            .values(revoked_at=now)
        ),
    ).rowcount
    session.execute(
        update(Webhook)
        .where(Webhook.machine_id == machine.id, Webhook.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    session.execute(
        delete(MachineDeviceSubscription).where(MachineDeviceSubscription.machine_id == machine.id)
    )
    session.execute(
        update(LiveActivityBinding)
        .where(
            LiveActivityBinding.run_id.in_(_machine_run_ids(machine.id)),
            LiveActivityBinding.invalidated_at.is_(None),
        )
        .values(
            state="invalidated",
            invalidated_at=now,
            ended_at=now,
            update_push_token_encrypted=None,
        )
    )
    machine.revoked_at = now
    _audit(
        session,
        principal,
        "machine.revoke",
        {
            "machine_id": machine.id,
            "credentials_revoked": int(credential_count or 0),
            "cancelled_pushes": cancelled,
        },
    )
    bump_workspace_revision(session, machine.workspace_id)


@router.post("/machines/{machine_id}/revoke", status_code=status.HTTP_204_NO_CONTENT)
def revoke_machine(
    machine_id: str,
    session: Session = Depends(get_session),
    principal: Principal = Depends(authenticate),
) -> Response:
    _require_device(principal)
    machine = session.get(Machine, machine_id)
    if machine is None or machine.workspace_id != principal.workspace_id:
        _error(status.HTTP_404_NOT_FOUND, "machine_not_found", "machine not found")
    if machine.revoked_at is None:
        _revoke_machine(session, principal, machine)
        session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/machines/{machine_id}/revoke-self", status_code=status.HTTP_204_NO_CONTENT)
def revoke_machine_self(
    machine_id: str,
    session: Session = Depends(get_session),
    principal: Principal = Depends(authenticate),
) -> Response:
    _require_machine(principal)
    if principal.subject_id != machine_id:
        _error(
            status.HTTP_403_FORBIDDEN,
            "machine_ownership_mismatch",
            "machine ownership mismatch",
        )
    machine = session.get(Machine, machine_id)
    if machine is None or machine.workspace_id != principal.workspace_id:
        _error(status.HTTP_404_NOT_FOUND, "machine_not_found", "machine not found")
    if machine.revoked_at is None:
        _revoke_machine(session, principal, machine)
        session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/devices/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
def reset_device(
    device_id: str,
    session: Session = Depends(get_session),
    principal: Principal = Depends(authenticate),
) -> Response:
    _require_device(principal)
    if principal.subject_id != device_id:
        _error(status.HTTP_403_FORBIDDEN, "device_ownership_mismatch", "device ownership mismatch")
    device = session.get(Device, device_id)
    if device is None or device.workspace_id != principal.workspace_id:
        _error(status.HTTP_404_NOT_FOUND, "device_not_found", "device not found")
    now = utcnow()
    binding_ids = list(
        session.scalars(
            select(LiveActivityBinding.id).where(LiveActivityBinding.device_id == device_id)
        )
    )
    target_filter: ColumnElement[bool] = (PushOutbox.target_type == "device") & (
        PushOutbox.target_id == device_id
    )
    if binding_ids:
        target_filter = or_(
            target_filter,
            (PushOutbox.target_type == "activity") & PushOutbox.target_id.in_(binding_ids),
        )
    cancelled = cast(
        CursorResult[Any],
        session.execute(
            update(PushOutbox)
            .where(PushOutbox.status == "pending", target_filter)
            .values(status="cancelled", last_error="device reset", updated_at=now)
        ),
    ).rowcount
    session.execute(
        update(DeviceCredential)
        .where(
            DeviceCredential.device_id == device_id,
            DeviceCredential.revoked_at.is_(None),
        )
        .values(revoked_at=now)
    )
    session.execute(
        update(LiveActivityBinding)
        .where(LiveActivityBinding.device_id == device_id)
        .values(
            state="invalidated",
            invalidated_at=now,
            ended_at=now,
            update_push_token_encrypted=None,
        )
    )
    session.execute(
        delete(MachineDeviceSubscription).where(MachineDeviceSubscription.device_id == device_id)
    )
    session.execute(
        delete(WorkspaceDeletionChallenge).where(WorkspaceDeletionChallenge.device_id == device_id)
    )
    device.notification_token_encrypted = None
    device.push_to_start_token_encrypted = None
    _audit(
        session,
        principal,
        "device.reset",
        {"cancelled_pushes": int(cancelled or 0)},
    )
    # Bump before this Device's credential is revoked in the same transaction
    # so other Devices never keep a stale subscription projection.
    bump_workspace_revision(session, principal.workspace_id)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/workspaces/{workspace_id}/deletion-challenge")
def create_workspace_deletion_challenge(
    workspace_id: str,
    body: DeletionChallengeRequest,
    request: Request,
    session: Session = Depends(get_session),
    principal: Principal = Depends(authenticate),
) -> dict[str, Any]:
    _require_device(principal)
    if workspace_id != principal.workspace_id:
        _error(status.HTTP_404_NOT_FOUND, "workspace_not_found", "workspace not found")
    if body.confirmation != "DELETE":
        _error(
            status.HTTP_409_CONFLICT,
            "confirmation_mismatch",
            "confirmation must be DELETE",
        )
    # Serialize challenge rotation per Device on PostgreSQL. The unique
    # workspace/device constraint is the final guard against concurrent rows.
    session.scalar(select(Device).where(Device.id == principal.subject_id).with_for_update())
    now = utcnow()
    expires_at = now + timedelta(
        seconds=_settings(request).workspace_deletion_challenge_ttl_seconds
    )
    session.execute(
        delete(WorkspaceDeletionChallenge).where(
            WorkspaceDeletionChallenge.workspace_id == workspace_id,
            WorkspaceDeletionChallenge.device_id == principal.subject_id,
        )
    )
    raw_challenge = new_bearer_token("rbdc")
    session.add(
        WorkspaceDeletionChallenge(
            id=new_id("wdc"),
            workspace_id=workspace_id,
            device_id=principal.subject_id,
            token_hash=token_hash(raw_challenge, _settings(request).credential_pepper),
            expires_at=expires_at,
        )
    )
    _audit(session, principal, "workspace.deletion_challenge")
    session.commit()
    return {"challenge": raw_challenge, "expires_at": expires_at}


@router.delete("/workspaces/{workspace_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_workspace(
    workspace_id: str,
    body: WorkspaceDeleteRequest,
    request: Request,
    session: Session = Depends(get_session),
    principal: Principal = Depends(authenticate),
) -> Response:
    _require_device(principal)
    if workspace_id != principal.workspace_id:
        _error(status.HTTP_404_NOT_FOUND, "workspace_not_found", "workspace not found")
    digest = token_hash(body.challenge, _settings(request).credential_pepper)
    challenge = session.scalar(
        select(WorkspaceDeletionChallenge).where(
            WorkspaceDeletionChallenge.workspace_id == workspace_id,
            WorkspaceDeletionChallenge.device_id == principal.subject_id,
            WorkspaceDeletionChallenge.consumed_at.is_(None),
        )
    )
    if challenge is None or not hmac.compare_digest(challenge.token_hash, digest):
        _error(
            status.HTTP_409_CONFLICT,
            "invalid_deletion_challenge",
            "deletion challenge is invalid",
        )
    if is_expired(challenge.expires_at):
        session.delete(challenge)
        session.commit()
        _error(
            status.HTTP_409_CONFLICT,
            "expired_deletion_challenge",
            "deletion challenge has expired",
        )

    workspace = session.scalar(
        select(Workspace).where(Workspace.id == workspace_id).with_for_update()
    )
    if workspace is None:
        _error(status.HTTP_404_NOT_FOUND, "workspace_not_found", "workspace not found")
    challenge.consumed_at = utcnow()
    session.flush()
    _delete_workspace_rows(session, _settings(request), workspace_id)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _delete_workspace_rows(session: Session, settings: Settings, workspace_id: str) -> None:
    """Delete a workspace and every bearer/data row in the caller transaction."""

    device_ids = list(session.scalars(select(Device.id).where(Device.workspace_id == workspace_id)))
    installation_ids = list(
        session.scalars(select(Device.installation_id).where(Device.workspace_id == workspace_id))
    )
    machine_ids = list(
        session.scalars(select(Machine.id).where(Machine.workspace_id == workspace_id))
    )
    webhook_ids = list(
        session.scalars(select(Webhook.id).where(Webhook.workspace_id == workspace_id))
    )
    pairing_ids = list(
        session.scalars(
            select(PairingSession.id).where(PairingSession.workspace_id == workspace_id)
        )
    )
    run_ids = list(session.scalars(select(Run.id).where(Run.workspace_id == workspace_id)))
    binding_ids = (
        list(
            session.scalars(
                select(LiveActivityBinding.id).where(
                    or_(
                        LiveActivityBinding.device_id.in_(device_ids),
                        LiveActivityBinding.run_id.in_(run_ids),
                    )
                )
            )
        )
        if device_ids or run_ids
        else []
    )
    outbox_filters: list[ColumnElement[bool]] = [PushOutbox.run_id.in_(run_ids)] if run_ids else []
    if device_ids:
        outbox_filters.append(
            (PushOutbox.target_type == "device") & PushOutbox.target_id.in_(device_ids)
        )
    if binding_ids:
        outbox_filters.append(
            (PushOutbox.target_type == "activity") & PushOutbox.target_id.in_(binding_ids)
        )
    outbox_ids = (
        list(session.scalars(select(PushOutbox.id).where(or_(*outbox_filters))))
        if outbox_filters
        else []
    )

    # Remove only derived abuse-control rows that can be attributed exactly to
    # this Workspace. Anonymous IP buckets/locks may be shared and are retained.
    rate_subject_keys = {
        anonymized_key(settings, "workspace", workspace_id),
        *(anonymized_key(settings, "machine", machine_id) for machine_id in machine_ids),
        *(anonymized_key(settings, "webhook", webhook_id) for webhook_id in webhook_ids),
        *(anonymized_key(settings, "pairing_session", pairing_id) for pairing_id in pairing_ids),
    }
    quota_lock_keys = {
        f"{namespace}:{anonymized_key(settings, namespace, workspace_id)}"
        for namespace in (
            "workspace_machines",
            "workspace_webhooks",
            "workspace_notifications",
        )
    }
    quota_lock_keys.update(
        f"machine_active_runs:{anonymized_key(settings, 'machine_active_runs', machine_id)}"
        for machine_id in machine_ids
    )
    quota_lock_keys.update(
        f"device_bootstrap:{anonymized_key(settings, 'device_bootstrap', installation_id)}"
        for installation_id in installation_ids
    )
    session.execute(
        delete(RateLimitBucket).where(RateLimitBucket.subject_key.in_(rate_subject_keys))
    )
    session.execute(delete(QuotaLock).where(QuotaLock.lock_key.in_(quota_lock_keys)))

    if outbox_ids:
        session.execute(delete(PushAttempt).where(PushAttempt.outbox_id.in_(outbox_ids)))
        session.execute(delete(PushOutbox).where(PushOutbox.id.in_(outbox_ids)))
    if run_ids:
        session.execute(delete(RunEvent).where(RunEvent.run_id.in_(run_ids)))
        session.execute(delete(LiveActivityBinding).where(LiveActivityBinding.run_id.in_(run_ids)))
    if machine_ids or device_ids:
        subscription_filters: list[ColumnElement[bool]] = []
        if machine_ids:
            subscription_filters.append(MachineDeviceSubscription.machine_id.in_(machine_ids))
        if device_ids:
            subscription_filters.append(MachineDeviceSubscription.device_id.in_(device_ids))
        session.execute(delete(MachineDeviceSubscription).where(or_(*subscription_filters)))
    session.execute(delete(Notification).where(Notification.workspace_id == workspace_id))
    session.execute(delete(Webhook).where(Webhook.workspace_id == workspace_id))
    session.execute(delete(PairingSession).where(PairingSession.workspace_id == workspace_id))
    session.execute(
        delete(WorkspaceDeletionChallenge).where(
            WorkspaceDeletionChallenge.workspace_id == workspace_id
        )
    )
    session.execute(delete(AuditLog).where(AuditLog.workspace_id == workspace_id))
    if device_ids:
        session.execute(delete(DeviceCredential).where(DeviceCredential.device_id.in_(device_ids)))
    if machine_ids:
        session.execute(
            delete(MachineCredential).where(MachineCredential.machine_id.in_(machine_ids))
        )
    if run_ids:
        session.execute(delete(Run).where(Run.id.in_(run_ids)))
    session.execute(delete(Device).where(Device.workspace_id == workspace_id))
    session.execute(delete(Machine).where(Machine.workspace_id == workspace_id))
    session.execute(delete(Workspace).where(Workspace.id == workspace_id))
