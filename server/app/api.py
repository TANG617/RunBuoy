from __future__ import annotations

import secrets
import uuid
from datetime import timedelta
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .auth import DEVICE_SCOPES, MACHINE_SCOPES, Principal, require_scope
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
    Run,
    RunEvent,
    Webhook,
    Workspace,
    utcnow,
)
from .schemas import (
    ActivitySyncRequest,
    ActivityTokenRegistration,
    DeviceBootstrapRequest,
    DevicePreferencesPatch,
    EventBatch,
    MachineMetadata,
    NotificationCreate,
    PairingClaim,
    PairingExchange,
    RunUpsert,
    TokenRegistration,
    WebhookCreate,
    WebhookRunEvent,
)
from .schemas import (
    RunEvent as RunEventInput,
)
from .security import cipher_for, is_expired, new_bearer_token, new_id, token_hash
from .services import (
    TERMINAL_STATUSES,
    create_notification,
    deterministic_webhook_run_id,
    ingest_events,
    run_snapshot,
    schedule_binding_end,
)

router = APIRouter(prefix="/v1")


def settings_for(request: Request) -> Settings:
    return request.app.state.settings


def _bearer_value(authorization: str | None) -> str:
    if authorization is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer credential")
    scheme, separator, value = authorization.partition(" ")
    if not separator or scheme.lower() != "bearer" or not value:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid authorization header")
    return value


def _device_owned(session: Session, principal: Principal, device_id: str) -> Device:
    if principal.kind != "device" or principal.subject_id != device_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "device ownership mismatch")
    device = session.get(Device, device_id)
    if device is None or device.revoked_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "device not found")
    return device


def _machine_owned(session: Session, principal: Principal, machine_id: str) -> Machine:
    if principal.kind != "machine" or principal.subject_id != machine_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "machine ownership mismatch")
    machine = session.get(Machine, machine_id)
    if machine is None or machine.revoked_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "machine not found")
    return machine


def _webhook_auth(
    session: Session,
    settings: Settings,
    hook_id: str,
    authorization: str | None,
) -> Webhook:
    webhook = session.get(Webhook, hook_id)
    supplied = _bearer_value(authorization)
    if (
        webhook is None
        or webhook.revoked_at is not None
        or webhook.token_hash != token_hash(supplied, settings.credential_pepper)
    ):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid webhook credential")
    return webhook


@router.post("/devices/bootstrap", status_code=status.HTTP_201_CREATED)
def bootstrap_device(
    body: DeviceBootstrapRequest,
    request: Request,
    session: Session = Depends(get_session),
) -> dict[str, str]:
    settings = settings_for(request)
    device = session.scalar(select(Device).where(Device.installation_id == body.installation_id))
    now = utcnow()
    if device is None:
        workspace = Workspace(id=new_id("wsp"))
        session.add(workspace)
        session.flush()
        device = Device(
            id=new_id("dev"),
            workspace_id=workspace.id,
            installation_id=body.installation_id,
            app_version=body.app_version,
            os_version=body.os_version,
        )
        session.add(device)
        session.flush()
    else:
        device.app_version = body.app_version
        device.os_version = body.os_version
        device.last_seen_at = now
        for credential in device.credentials:
            if credential.revoked_at is None:
                credential.revoked_at = now

    raw_token = new_bearer_token("rbd")
    session.add(
        DeviceCredential(
            id=new_id("dcr"),
            device_id=device.id,
            token_hash=token_hash(raw_token, settings.credential_pepper),
            scopes=" ".join(sorted(DEVICE_SCOPES)),
        )
    )
    # Materialize the workspace/device first so PostgreSQL can enforce the audit
    # log foreign key even though AuditLog intentionally has no ORM relationship.
    session.flush()
    session.add(
        AuditLog(
            id=new_id("aud"),
            workspace_id=device.workspace_id,
            actor_type="device",
            actor_id=device.id,
            action="device.bootstrap",
        )
    )
    session.commit()
    return {
        "device_id": device.id,
        "workspace_id": device.workspace_id,
        "credential": raw_token,
    }


@router.put("/devices/{device_id}/notification-token", status_code=status.HTTP_204_NO_CONTENT)
def register_notification_token(
    device_id: str,
    body: TokenRegistration,
    request: Request,
    session: Session = Depends(get_session),
    principal: Principal = Depends(require_scope("devices:register-token")),
) -> Response:
    device = _device_owned(session, principal, device_id)
    if body.generation is not None and body.generation < device.notification_token_generation:
        raise HTTPException(status.HTTP_409_CONFLICT, "stale token generation")
    device.notification_token_encrypted = cipher_for(settings_for(request)).encrypt(body.token)
    device.notification_token_generation = (
        body.generation or device.notification_token_generation + 1
    )
    device.last_seen_at = utcnow()
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/devices/{device_id}/push-to-start-token", status_code=status.HTTP_204_NO_CONTENT)
def register_push_to_start_token(
    device_id: str,
    body: TokenRegistration,
    request: Request,
    session: Session = Depends(get_session),
    principal: Principal = Depends(require_scope("live-activities:register-token")),
) -> Response:
    device = _device_owned(session, principal, device_id)
    if body.generation is not None and body.generation < device.push_to_start_token_generation:
        raise HTTPException(status.HTTP_409_CONFLICT, "stale token generation")
    device.push_to_start_token_encrypted = cipher_for(settings_for(request)).encrypt(body.token)
    device.push_to_start_token_generation = (
        body.generation or device.push_to_start_token_generation + 1
    )
    device.last_seen_at = utcnow()
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/devices/{device_id}/activity-sync", status_code=status.HTTP_204_NO_CONTENT)
def sync_activities(
    device_id: str,
    body: ActivitySyncRequest,
    request: Request,
    session: Session = Depends(get_session),
    principal: Principal = Depends(require_scope("live-activities:register-token")),
) -> Response:
    _device_owned(session, principal, device_id)
    cipher = cipher_for(settings_for(request))
    supplied_ids = {item.activity_id for item in body.activities}
    for item in body.activities:
        run = session.get(Run, item.run_id)
        if run is None or run.workspace_id != principal.workspace_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "run not found")
        binding = session.scalar(
            select(LiveActivityBinding).where(
                LiveActivityBinding.device_id == device_id,
                LiveActivityBinding.activity_id == item.activity_id,
            )
        )
        if binding is None:
            placeholder = session.scalar(
                select(LiveActivityBinding).where(
                    LiveActivityBinding.device_id == device_id,
                    LiveActivityBinding.run_id == item.run_id,
                    LiveActivityBinding.activity_id.like("pending:%"),
                    LiveActivityBinding.state == "active",
                )
            )
            if placeholder is not None:
                placeholder.state = "replaced"
                placeholder.ended_at = utcnow()
            binding = LiveActivityBinding(
                id=new_id("lab"),
                run_id=item.run_id,
                device_id=device_id,
                activity_id=item.activity_id,
            )
            session.add(binding)
        binding.state = item.state
        binding.last_sequence = item.last_sequence
        if item.update_token is not None and item.token_generation >= (
            binding.token_generation or 0
        ):
            binding.update_push_token_encrypted = cipher.encrypt(item.update_token)
            binding.token_generation = item.token_generation
            if run.execution_status in TERMINAL_STATUSES:
                schedule_binding_end(session, run, binding)
        if item.state != "active":
            binding.ended_at = utcnow()
    existing = list(
        session.scalars(
            select(LiveActivityBinding).where(
                LiveActivityBinding.device_id == device_id,
                LiveActivityBinding.state == "active",
                ~LiveActivityBinding.activity_id.like("pending:%"),
            )
        )
    )
    for binding in existing:
        if binding.activity_id not in supplied_ids:
            binding.state = "ended"
            binding.ended_at = utcnow()
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put(
    "/live-activities/{activity_id}/update-token",
    status_code=status.HTTP_204_NO_CONTENT,
)
def register_activity_update_token(
    activity_id: str,
    body: ActivityTokenRegistration,
    request: Request,
    session: Session = Depends(get_session),
    principal: Principal = Depends(require_scope("live-activities:register-token")),
) -> Response:
    _device_owned(session, principal, body.device_id)
    run = session.get(Run, body.run_id)
    if run is None or run.workspace_id != principal.workspace_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "run not found")
    binding = session.scalar(
        select(LiveActivityBinding).where(
            LiveActivityBinding.device_id == body.device_id,
            LiveActivityBinding.activity_id == activity_id,
        )
    )
    if binding is None:
        placeholder = session.scalar(
            select(LiveActivityBinding).where(
                LiveActivityBinding.device_id == body.device_id,
                LiveActivityBinding.run_id == body.run_id,
                LiveActivityBinding.activity_id.like("pending:%"),
                LiveActivityBinding.state == "active",
            )
        )
        if placeholder is not None:
            placeholder.state = "replaced"
            placeholder.ended_at = utcnow()
        binding = LiveActivityBinding(
            id=new_id("lab"),
            run_id=body.run_id,
            device_id=body.device_id,
            activity_id=activity_id,
        )
        session.add(binding)
    if (body.generation or 1) >= (binding.token_generation or 0):
        binding.update_push_token_encrypted = cipher_for(settings_for(request)).encrypt(body.token)
        binding.token_generation = body.generation or 1
        binding.invalidated_at = None
        binding.state = "active"
        if run.execution_status in TERMINAL_STATUSES:
            schedule_binding_end(session, run, binding)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch("/device-preferences")
def update_preferences(
    body: DevicePreferencesPatch,
    session: Session = Depends(get_session),
    principal: Principal = Depends(require_scope("preferences:write")),
) -> dict[str, bool]:
    device = _device_owned(session, principal, principal.subject_id)
    updates = body.model_dump(exclude_none=True)
    for key, value in updates.items():
        setattr(device, key, value)
    session.commit()
    return {
        "live_activities_enabled": device.live_activities_enabled,
        "failure_notifications_enabled": device.failure_notifications_enabled,
        "success_notifications_enabled": device.success_notifications_enabled,
    }


@router.delete(
    "/machine-subscriptions/{subscription_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_subscription(
    subscription_id: str,
    session: Session = Depends(get_session),
    principal: Principal = Depends(require_scope("subscriptions:delete")),
) -> Response:
    subscription = session.get(MachineDeviceSubscription, subscription_id)
    if subscription is None or subscription.device_id != principal.subject_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "subscription not found")
    session.delete(subscription)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/pairing-sessions", status_code=status.HTTP_201_CREATED)
def create_pairing_session(
    body: MachineMetadata,
    request: Request,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    settings = settings_for(request)
    raw_secret = new_bearer_token("rbx")
    pairing = PairingSession(
        id=new_id("pair"),
        challenge=secrets.token_urlsafe(24),
        short_code=f"{secrets.randbelow(1_000_000):06d}",
        exchange_secret_hash=token_hash(raw_secret, settings.credential_pepper),
        requested_machine_metadata=body.model_dump(),
        expires_at=utcnow() + timedelta(seconds=settings.pairing_ttl_seconds),
    )
    session.add(pairing)
    session.commit()
    return {
        "pairing_session_id": pairing.id,
        "challenge": pairing.challenge,
        "short_code": pairing.short_code,
        "exchange_secret": raw_secret,
        "expires_at": pairing.expires_at,
    }


@router.get("/pairing-sessions/{session_id}")
def get_pairing_session(
    session_id: str,
    request: Request,
    authorization: str | None = Header(default=None),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    pairing = session.get(PairingSession, session_id)
    supplied = _bearer_value(authorization)
    if pairing is None or pairing.exchange_secret_hash != token_hash(
        supplied, settings_for(request).credential_pepper
    ):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid pairing secret")
    if is_expired(pairing.expires_at):
        raise HTTPException(status.HTTP_410_GONE, "pairing session expired")
    return {
        "status": (
            "exchanged" if pairing.exchanged_at else "claimed" if pairing.claimed_at else "pending"
        ),
        "machine_id": pairing.machine_id,
        "expires_at": pairing.expires_at,
    }


@router.post("/pairing-sessions/{session_id}/claim")
def claim_pairing_session(
    session_id: str,
    body: PairingClaim,
    session: Session = Depends(get_session),
    principal: Principal = Depends(require_scope("pairing:claim")),
) -> dict[str, Any]:
    pairing = session.get(PairingSession, session_id)
    if pairing is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "pairing session not found")
    if is_expired(pairing.expires_at):
        raise HTTPException(status.HTTP_410_GONE, "pairing session expired")
    if pairing.claimed_at is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "pairing session already claimed")
    if not secrets.compare_digest(pairing.challenge, body.challenge):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "pairing challenge mismatch")
    metadata = pairing.requested_machine_metadata
    machine_id = metadata.get("machine_id") or new_id("mac")
    if session.get(Machine, machine_id) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "machine ID is already paired")
    machine = Machine(
        id=machine_id,
        workspace_id=principal.workspace_id,
        display_name=metadata["display_name"],
        hostname=metadata.get("hostname"),
        platform=metadata.get("platform"),
        architecture=metadata.get("architecture"),
        cli_version=metadata.get("cli_version"),
    )
    subscription = MachineDeviceSubscription(
        id=new_id("sub"),
        machine_id=machine.id,
        device_id=principal.subject_id,
    )
    pairing.claimed_at = utcnow()
    pairing.workspace_id = principal.workspace_id
    pairing.machine_id = machine.id
    session.add_all([machine, subscription])
    session.commit()
    return {
        "status": "claimed",
        "machine_id": machine.id,
        "machine": metadata,
    }


@router.post("/pairing-sessions/{session_id}/exchange")
def exchange_pairing_session(
    session_id: str,
    body: PairingExchange,
    request: Request,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    settings = settings_for(request)
    pairing = session.get(PairingSession, session_id)
    if pairing is None or pairing.exchange_secret_hash != token_hash(
        body.exchange_secret, settings.credential_pepper
    ):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid pairing secret")
    if is_expired(pairing.expires_at):
        raise HTTPException(status.HTTP_410_GONE, "pairing session expired")
    if pairing.claimed_at is None or pairing.machine_id is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "pairing session is not claimed")
    if pairing.exchanged_at is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "pairing secret already exchanged")
    raw_token = new_bearer_token("rbm")
    session.add(
        MachineCredential(
            id=new_id("mcr"),
            machine_id=pairing.machine_id,
            token_hash=token_hash(raw_token, settings.credential_pepper),
            scopes=" ".join(sorted(MACHINE_SCOPES)),
        )
    )
    pairing.exchanged_at = utcnow()
    session.commit()
    return {
        "machine_id": pairing.machine_id,
        "workspace_id": pairing.workspace_id,
        "credential": raw_token,
    }


@router.put("/runs/{run_id}")
def upsert_run(
    run_id: uuid.UUID,
    body: RunUpsert,
    session: Session = Depends(get_session),
    principal: Principal = Depends(require_scope("runs:create")),
) -> dict[str, Any]:
    machine = _machine_owned(session, principal, body.machine_id)
    machine.last_seen_at = utcnow()
    if body.cli_version is not None:
        machine.cli_version = body.cli_version
    key = str(run_id)
    run = session.get(Run, key)
    if run is None:
        run = Run(
            id=key,
            workspace_id=principal.workspace_id,
            machine_id=body.machine_id,
            title=body.title,
            source=body.source,
            # PUT registers safe metadata only. Ordered events are the sole
            # authority for execution/progress projection, including offline
            # terminal replay where the local snapshot is already terminal.
            execution_status="CREATED",
            health_status="HEALTHY",
            attention_status="NONE",
            progress=None,
            phase=None,
            safe_message=None,
            started_at=None,
            live_activity_policy=body.live_activity_policy,
            notification_policy=body.notification_policy,
        )
        session.add(run)
    else:
        if run.machine_id != principal.subject_id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "run ownership mismatch")
        if (
            run.execution_status in TERMINAL_STATUSES
            and body.execution_status != run.execution_status
        ):
            raise HTTPException(status.HTTP_409_CONFLICT, "terminal run state is immutable")
        run.title = body.title
        run.source = body.source
        run.health_status = body.health_status
        run.attention_status = body.attention_status
        run.live_activity_policy = body.live_activity_policy
        run.notification_policy = body.notification_policy
    session.commit()
    return run_snapshot(run)


@router.post("/runs/{run_id}/events:batch")
def ingest_run_events(
    run_id: uuid.UUID,
    body: EventBatch,
    request: Request,
    session: Session = Depends(get_session),
    principal: Principal = Depends(require_scope("events:write")),
) -> dict[str, Any]:
    run = session.get(Run, str(run_id))
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "run not found")
    _machine_owned(session, principal, run.machine_id)
    try:
        result = ingest_events(session, settings_for(request), run, body.events)
        session.commit()
        return result
    except Exception:
        session.rollback()
        raise


@router.get("/runs")
def list_runs(
    session: Session = Depends(get_session),
    principal: Principal = Depends(require_scope("runs:read")),
) -> list[dict[str, Any]]:
    runs = list(
        session.scalars(
            select(Run)
            .where(Run.workspace_id == principal.workspace_id)
            .order_by(Run.updated_at.desc())
            .limit(200)
        )
    )
    return [run_snapshot(run) for run in runs]


@router.get("/runs/{run_id}")
def get_run(
    run_id: uuid.UUID,
    session: Session = Depends(get_session),
    principal: Principal = Depends(require_scope("runs:read")),
) -> dict[str, Any]:
    run = session.get(Run, str(run_id))
    if run is None or run.workspace_id != principal.workspace_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "run not found")
    result = run_snapshot(run)
    events = list(
        session.scalars(
            select(RunEvent).where(RunEvent.run_id == run.id).order_by(RunEvent.seq).limit(500)
        )
    )
    events_payload = [
        {
            "event_id": event.event_id,
            "seq": event.seq,
            "type": event.type,
            "occurred_at": event.occurred_at,
            "received_at": event.received_at,
            "payload": event.payload,
        }
        for event in events
    ]
    return {"run": result, "events": events_payload}


@router.get("/machines")
def list_machines(
    session: Session = Depends(get_session),
    principal: Principal = Depends(require_scope("machines:read")),
) -> list[dict[str, Any]]:
    machines = list(
        session.scalars(
            select(Machine)
            .where(Machine.workspace_id == principal.workspace_id, Machine.revoked_at.is_(None))
            .order_by(Machine.paired_at.desc())
        )
    )
    return [
        {
            "id": machine.id,
            "display_name": machine.display_name,
            "platform": machine.platform,
            "architecture": machine.architecture,
            "cli_version": machine.cli_version,
            "last_seen_at": machine.last_seen_at,
            "paired_at": machine.paired_at,
            "subscription_id": (
                subscription.id
                if (
                    subscription := session.scalar(
                        select(MachineDeviceSubscription).where(
                            MachineDeviceSubscription.machine_id == machine.id,
                            MachineDeviceSubscription.device_id == principal.subject_id,
                        )
                    )
                )
                else None
            ),
            "is_subscribed": session.scalar(
                select(MachineDeviceSubscription.id).where(
                    MachineDeviceSubscription.machine_id == machine.id,
                    MachineDeviceSubscription.device_id == principal.subject_id,
                )
            )
            is not None,
        }
        for machine in machines
    ]


@router.get("/notifications")
def list_notifications(
    session: Session = Depends(get_session),
    principal: Principal = Depends(require_scope("notifications:read")),
) -> list[dict[str, Any]]:
    notifications = list(
        session.scalars(
            select(Notification)
            .where(Notification.workspace_id == principal.workspace_id)
            .order_by(Notification.created_at.desc())
            .limit(200)
        )
    )
    return [
        {
            "id": item.id,
            "machine_id": item.machine_id,
            "run_id": item.run_id,
            "title": item.title,
            "subtitle": item.subtitle,
            "body": item.body,
            "level": item.level,
            "fields": item.fields,
            "safe_link": item.safe_link,
            "created_at": item.created_at,
            "expires_at": item.expires_at,
        }
        for item in notifications
    ]


@router.post("/notifications", status_code=status.HTTP_201_CREATED)
def post_notification(
    body: NotificationCreate,
    session: Session = Depends(get_session),
    principal: Principal = Depends(require_scope("notifications:send")),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict[str, Any]:
    notification = create_notification(
        session,
        workspace_id=principal.workspace_id,
        machine_id=principal.subject_id,
        body=body,
        dedupe_key=f"api:{principal.subject_id}:{idempotency_key}" if idempotency_key else None,
    )
    session.commit()
    return {"id": notification.id, "created_at": notification.created_at}


@router.post("/webhooks", status_code=status.HTTP_201_CREATED)
def create_webhook(
    body: WebhookCreate,
    request: Request,
    session: Session = Depends(get_session),
    principal: Principal = Depends(require_scope("hooks:manage")),
) -> dict[str, str]:
    raw_secret = new_bearer_token("rbh")
    webhook = Webhook(
        id=new_id("hook"),
        workspace_id=principal.workspace_id,
        machine_id=principal.subject_id,
        name=body.name,
        token_hash=token_hash(raw_secret, settings_for(request).credential_pepper),
    )
    session.add(webhook)
    session.commit()
    return {"hook_id": webhook.id, "secret": raw_secret}


@router.delete("/webhooks/{hook_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_webhook(
    hook_id: str,
    session: Session = Depends(get_session),
    principal: Principal = Depends(require_scope("hooks:manage")),
) -> Response:
    webhook = session.get(Webhook, hook_id)
    if webhook is None or webhook.machine_id != principal.subject_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "webhook not found")
    webhook.revoked_at = utcnow()
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/hooks/{hook_id}/notifications", status_code=status.HTTP_201_CREATED)
def webhook_notification(
    hook_id: str,
    body: NotificationCreate,
    request: Request,
    authorization: str | None = Header(default=None),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    session: Session = Depends(get_session),
) -> dict[str, str]:
    webhook = _webhook_auth(session, settings_for(request), hook_id, authorization)
    notification = create_notification(
        session,
        workspace_id=webhook.workspace_id,
        machine_id=webhook.machine_id,
        body=body,
        dedupe_key=f"hook:{hook_id}:{idempotency_key}" if idempotency_key else None,
    )
    session.commit()
    return {"id": notification.id}


@router.put("/hooks/{hook_id}/runs/{external_run_id}")
def webhook_run_upsert(
    hook_id: str,
    external_run_id: str,
    body: RunUpsert,
    request: Request,
    authorization: str | None = Header(default=None),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    webhook = _webhook_auth(session, settings_for(request), hook_id, authorization)
    if body.machine_id != webhook.machine_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "webhook machine mismatch")
    run_id = deterministic_webhook_run_id(hook_id, external_run_id)
    run = session.get(Run, run_id)
    if run is None:
        run = Run(
            id=run_id,
            workspace_id=webhook.workspace_id,
            machine_id=webhook.machine_id,
            title=body.title,
            source=body.source or "webhook",
            execution_status=body.execution_status,
            health_status=body.health_status,
            attention_status=body.attention_status,
            progress=body.progress,
            phase=body.phase,
            safe_message=body.safe_message,
            started_at=body.started_at,
            live_activity_policy=body.live_activity_policy,
            notification_policy=body.notification_policy,
            external_key=f"{hook_id}:{external_run_id}",
        )
        session.add(run)
    else:
        if run.execution_status in TERMINAL_STATUSES:
            raise HTTPException(status.HTTP_409_CONFLICT, "terminal run state is immutable")
        run.title = body.title
        run.source = body.source or run.source
    session.commit()
    return run_snapshot(run)


@router.post("/hooks/{hook_id}/runs/{external_run_id}/events", status_code=status.HTTP_202_ACCEPTED)
def webhook_run_event(
    hook_id: str,
    external_run_id: str,
    body: WebhookRunEvent,
    request: Request,
    authorization: str | None = Header(default=None),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    webhook = _webhook_auth(session, settings_for(request), hook_id, authorization)
    run_id = deterministic_webhook_run_id(hook_id, external_run_id)
    run = session.get(Run, run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "webhook run not found")
    event_uuid = (
        uuid.uuid5(uuid.NAMESPACE_URL, f"{hook_id}:{idempotency_key}")
        if idempotency_key
        else uuid.uuid4()
    )
    payload = body.model_dump(
        exclude={"type", "occurred_at"},
        exclude_none=True,
    )
    event = RunEventInput(
        schema_version=1,
        event_id=event_uuid,
        run_id=uuid.UUID(run.id),
        machine_id=webhook.machine_id,
        seq=run.last_seq + 1,
        type=body.type,
        occurred_at=body.occurred_at or utcnow(),
        payload=payload,
    )
    result = ingest_events(session, settings_for(request), run, [event])
    session.commit()
    return result
