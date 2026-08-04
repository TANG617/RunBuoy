from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


class Workspace(Base):
    __tablename__ = "workspaces"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    installation_id: Mapped[str] = mapped_column(String(128), unique=True)
    app_version: Mapped[str | None] = mapped_column(String(64))
    os_version: Mapped[str | None] = mapped_column(String(64))
    notification_token_encrypted: Mapped[str | None] = mapped_column(Text)
    notification_token_generation: Mapped[int] = mapped_column(Integer, default=0)
    push_to_start_token_encrypted: Mapped[str | None] = mapped_column(Text)
    push_to_start_token_generation: Mapped[int] = mapped_column(Integer, default=0)
    live_activities_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    frequent_live_activity_updates_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default=true(),
    )
    failure_notifications_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    success_notifications_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default=true(),
    )
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    credentials: Mapped[list[DeviceCredential]] = relationship(
        back_populates="device", cascade="all, delete-orphan"
    )


class DeviceCredential(Base):
    __tablename__ = "device_credentials"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    scopes: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    device: Mapped[Device] = relationship(back_populates="credentials")


class Machine(Base):
    __tablename__ = "machines"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    display_name: Mapped[str] = mapped_column(String(120))
    hostname: Mapped[str | None] = mapped_column(String(255))
    platform: Mapped[str | None] = mapped_column(String(64))
    architecture: Mapped[str | None] = mapped_column(String(64))
    cli_version: Mapped[str | None] = mapped_column(String(64))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    paired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    credentials: Mapped[list[MachineCredential]] = relationship(
        back_populates="machine", cascade="all, delete-orphan"
    )


class MachineCredential(Base):
    __tablename__ = "machine_credentials"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    machine_id: Mapped[str] = mapped_column(ForeignKey("machines.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    scopes: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    machine: Mapped[Machine] = relationship(back_populates="credentials")


class MachineDeviceSubscription(Base):
    __tablename__ = "machine_device_subscriptions"
    __table_args__ = (UniqueConstraint("machine_id", "device_id"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    machine_id: Mapped[str] = mapped_column(ForeignKey("machines.id"), index=True)
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PairingSession(Base):
    __tablename__ = "pairing_sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    challenge: Mapped[str] = mapped_column(String(64), unique=True)
    short_code: Mapped[str] = mapped_column(String(6), index=True)
    exchange_secret_hash: Mapped[str] = mapped_column(String(64))
    requested_machine_metadata: Mapped[dict[str, Any]] = mapped_column(JSON)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    exchanged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    workspace_id: Mapped[str | None] = mapped_column(ForeignKey("workspaces.id"))
    machine_id: Mapped[str | None] = mapped_column(ForeignKey("machines.id"))


class Run(Base):
    __tablename__ = "runs"
    __table_args__ = (
        Index("ix_runs_workspace_status_started", "workspace_id", "execution_status", "started_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    machine_id: Mapped[str] = mapped_column(ForeignKey("machines.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    source: Mapped[str | None] = mapped_column(String(120))
    execution_status: Mapped[str] = mapped_column(String(32), default="CREATED")
    health_status: Mapped[str] = mapped_column(String(32), default="HEALTHY")
    attention_status: Mapped[str] = mapped_column(String(32), default="NONE")
    progress: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    phase: Mapped[str | None] = mapped_column(String(120))
    safe_message: Mapped[str | None] = mapped_column(String(500))
    safe_log_tail: Mapped[list[str] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    exit_code: Mapped[int | None] = mapped_column(Integer)
    termination_reason: Mapped[str | None] = mapped_column(String(120))
    live_activity_policy: Mapped[str] = mapped_column(String(32), default="automatic")
    notification_policy: Mapped[str] = mapped_column(String(32), default="failures")
    last_seq: Mapped[int] = mapped_column(Integer, default=0)
    external_key: Mapped[str | None] = mapped_column(String(255), unique=True)
    machine: Mapped[Machine] = relationship()


class RunEvent(Base):
    __tablename__ = "run_events"
    __table_args__ = (
        UniqueConstraint("run_id", "seq", name="uq_run_events_run_seq"),
        UniqueConstraint("event_id", name="uq_run_events_event_id"),
        Index("ix_run_events_run_seq", "run_id", "seq"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    schema_version: Mapped[int] = mapped_column(Integer)
    event_id: Mapped[str] = mapped_column(String(64))
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), index=True)
    machine_id: Mapped[str] = mapped_column(ForeignKey("machines.id"), index=True)
    seq: Mapped[int] = mapped_column(Integer)
    type: Mapped[str] = mapped_column(String(64))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (
        UniqueConstraint("workspace_id", "dedupe_key", name="uq_notifications_workspace_dedupe"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    machine_id: Mapped[str | None] = mapped_column(ForeignKey("machines.id"), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("runs.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    subtitle: Mapped[str | None] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(String(2000))
    level: Mapped[str] = mapped_column(String(16))
    fields: Mapped[list[dict[str, str]]] = mapped_column(JSON, default=list)
    safe_link: Mapped[str | None] = mapped_column(String(2048))
    dedupe_key: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class LiveActivityBinding(Base):
    __tablename__ = "live_activity_bindings"
    __table_args__ = (
        UniqueConstraint("device_id", "activity_id"),
        Index("ix_live_activity_run_device_state", "run_id", "device_id", "state"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), index=True)
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.id"), index=True)
    activity_id: Mapped[str] = mapped_column(String(255))
    update_push_token_encrypted: Mapped[str | None] = mapped_column(Text)
    token_generation: Mapped[int] = mapped_column(Integer, default=0)
    schema_version: Mapped[int] = mapped_column(Integer, default=1)
    state: Mapped[str] = mapped_column(String(32), default="active")
    last_sequence: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    invalidated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PushOutbox(Base):
    __tablename__ = "push_outbox"
    __table_args__ = (Index("ix_push_outbox_status_available", "status", "available_at"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    kind: Mapped[str] = mapped_column(String(32))
    target_type: Mapped[str] = mapped_column(String(32))
    target_id: Mapped[str] = mapped_column(String(64))
    run_id: Mapped[str | None] = mapped_column(ForeignKey("runs.id"), index=True)
    desired_payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    priority: Mapped[int] = mapped_column(Integer, default=5)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    last_error: Mapped[str | None] = mapped_column(String(500))
    coalesce_key: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PushAttempt(Base):
    __tablename__ = "push_attempts"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    outbox_id: Mapped[str] = mapped_column(ForeignKey("push_outbox.id"), index=True)
    attempted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    status_code: Mapped[int] = mapped_column(Integer)
    apns_id: Mapped[str | None] = mapped_column(String(64))
    reason: Mapped[str | None] = mapped_column(String(255))
    request_payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    request_headers: Mapped[dict[str, str]] = mapped_column(JSON)


class Webhook(Base):
    __tablename__ = "webhooks"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    machine_id: Mapped[str] = mapped_column(ForeignKey("machines.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workspace_id: Mapped[str | None] = mapped_column(ForeignKey("workspaces.id"), index=True)
    actor_type: Mapped[str] = mapped_column(String(32))
    actor_id: Mapped[str | None] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(120))
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
