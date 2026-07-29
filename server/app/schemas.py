from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator

ExecutionStatus = Literal[
    "CREATED", "STARTING", "RUNNING", "SUCCEEDED", "FAILED", "CANCELLED", "LOST"
]
HealthStatus = Literal["HEALTHY", "STALE", "OFFLINE"]
AttentionStatus = Literal["NONE", "INFORMATION", "WARNING", "ACTION_REQUIRED"]
EventType = Literal[
    "run.created",
    "run.starting",
    "run.started",
    "run.progress",
    "run.phase_changed",
    "run.message",
    "run.attention_required",
    "run.heartbeat",
    "run.succeeded",
    "run.failed",
    "run.cancelled",
    "run.lost",
]


class APIModel(BaseModel):
    model_config = ConfigDict(extra="ignore")


class DeviceBootstrapRequest(APIModel):
    installation_id: str = Field(min_length=1, max_length=128)
    app_version: str | None = Field(default=None, max_length=64)
    os_version: str | None = Field(default=None, max_length=64)


class TokenRegistration(APIModel):
    token: str = Field(min_length=8, max_length=4096)
    generation: int | None = Field(default=None, ge=1)


class DevicePreferencesPatch(APIModel):
    live_activities_enabled: bool | None = None
    failure_notifications_enabled: bool | None = None
    success_notifications_enabled: bool | None = None


class ActivitySyncItem(APIModel):
    activity_id: str = Field(min_length=1, max_length=255)
    run_id: str
    update_token: str | None = Field(default=None, min_length=8, max_length=4096)
    token_generation: int = Field(default=1, ge=1)
    state: Literal["active", "stale", "ended", "dismissed"] = "active"
    last_sequence: int = Field(default=0, ge=0)


class ActivitySyncRequest(APIModel):
    activities: list[ActivitySyncItem] = Field(default_factory=list, max_length=20)


class ActivityTokenRegistration(TokenRegistration):
    device_id: str
    run_id: str


class MachineMetadata(APIModel):
    machine_id: str | None = Field(default=None, min_length=1, max_length=128)
    display_name: str = Field(min_length=1, max_length=120)
    hostname: str | None = Field(default=None, max_length=255)
    platform: str | None = Field(default=None, max_length=64)
    architecture: str | None = Field(default=None, max_length=64)
    cli_version: str | None = Field(default=None, max_length=64)


class PairingClaim(APIModel):
    challenge: str = Field(min_length=16, max_length=128)


class PairingExchange(APIModel):
    exchange_secret: str = Field(min_length=16, max_length=256)


class RunUpsert(APIModel):
    machine_id: str
    title: str = Field(min_length=1, max_length=200)
    source: str | None = Field(default=None, max_length=120)
    cli_version: str | None = Field(default=None, max_length=64)
    execution_status: ExecutionStatus = "CREATED"
    health_status: HealthStatus = "HEALTHY"
    attention_status: AttentionStatus = "NONE"
    progress: dict[str, Any] | None = None
    phase: str | None = Field(default=None, max_length=120)
    safe_message: str | None = Field(default=None, max_length=500)
    started_at: datetime | None = None
    live_activity_policy: Literal["automatic", "disabled"] = "automatic"
    notification_policy: Literal["failures", "all", "none"] = "failures"


class RunEvent(APIModel):
    schema_version: Literal[1]
    event_id: UUID
    run_id: UUID
    machine_id: str = Field(min_length=1, max_length=128)
    seq: int = Field(ge=1)
    type: EventType
    occurred_at: datetime
    payload: dict[str, Any]

    @field_validator("occurred_at")
    @classmethod
    def timezone_required(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("occurred_at must include a timezone")
        return value

    @field_validator("payload")
    @classmethod
    def safe_payload_limits(cls, value: dict[str, Any]) -> dict[str, Any]:
        encoded = json.dumps(value, separators=(",", ":")).encode()
        if len(encoded) > 64 * 1024:
            raise ValueError("event payload exceeds 64 KiB")
        tail = value.get("safe_log_tail")
        if tail is not None:
            if not isinstance(tail, list) or len(tail) > 100:
                raise ValueError("safe_log_tail must contain at most 100 lines")
            if any(not isinstance(line, str) or len(line) > 500 for line in tail):
                raise ValueError("safe_log_tail lines must be strings of at most 500 characters")
        return value


class EventBatch(APIModel):
    events: list[RunEvent] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def unique_batch_keys(self) -> EventBatch:
        event_ids = [item.event_id for item in self.events]
        seqs = [item.seq for item in self.events]
        if len(event_ids) != len(set(event_ids)):
            raise ValueError("event_id must be unique within a batch")
        if len(seqs) != len(set(seqs)):
            raise ValueError("seq must be unique within a batch")
        return self


class RichField(APIModel):
    label: str = Field(min_length=1, max_length=80)
    value: str = Field(max_length=500)


class NotificationCreate(APIModel):
    title: str = Field(min_length=1, max_length=200)
    subtitle: str | None = Field(default=None, max_length=200)
    body: str = Field(min_length=1, max_length=2000)
    level: Literal["info", "success", "warning", "error"] = "info"
    fields: list[RichField] = Field(default_factory=list, max_length=20)
    safe_link: HttpUrl | None = None
    run_id: str | None = None
    expires_at: datetime | None = None

    @field_validator("safe_link")
    @classmethod
    def https_links_only(cls, value: HttpUrl | None) -> HttpUrl | None:
        if value is not None and value.scheme != "https":
            raise ValueError("safe_link must use HTTPS")
        return value


class WebhookCreate(APIModel):
    name: str = Field(min_length=1, max_length=120)


class WebhookRunEvent(APIModel):
    type: EventType
    occurred_at: datetime | None = None
    progress: dict[str, Any] | None = None
    phase: str | None = Field(default=None, max_length=120)
    message: str | None = Field(default=None, max_length=500)
    exit_code: int | None = None
    termination_reason: str | None = Field(default=None, max_length=120)
    attention_status: AttentionStatus | None = None
