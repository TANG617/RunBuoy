from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


def utc_now() -> datetime:
    return datetime.now(UTC)


class ExecutionStatus(StrEnum):
    CREATED = "CREATED"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    LOST = "LOST"


class ProgressMode(StrEnum):
    STRUCTURED = "structured"
    LINES = "lines"
    REGEX = "regex"
    INDETERMINATE = "indeterminate"


class LiveActivityPolicy(StrEnum):
    AUTOMATIC = "automatic"
    IMMEDIATE = "immediate"
    DISABLED = "disabled"


class Progress(BaseModel):
    model_config = ConfigDict(extra="allow")

    kind: Literal["determinate", "indeterminate"]
    source: Literal["explicit", "adapter", "regex", "lines", "unknown"]
    current: float | None = None
    total: float | None = None
    fraction: float | None = None
    unit: str | None = Field(default=None, max_length=40)
    phase: str | None = Field(default=None, max_length=120)
    message: str | None = Field(default=None, max_length=500)

    @field_validator("total")
    @classmethod
    def positive_total(cls, value: float | None) -> float | None:
        if value is not None and value <= 0:
            raise ValueError("total must be greater than zero")
        return value

    @classmethod
    def determinate(
        cls,
        current: float,
        total: float,
        *,
        source: Literal["explicit", "adapter", "regex", "lines"],
        unit: str | None = None,
        phase: str | None = None,
        message: str | None = None,
    ) -> Progress:
        if total <= 0:
            raise ValueError("total must be greater than zero")
        clamped = min(max(current, 0), total)
        return cls(
            kind="determinate",
            current=clamped,
            total=total,
            fraction=clamped / total,
            unit=unit,
            source=source,
            phase=phase,
            message=message,
        )


class RunEvent(BaseModel):
    model_config = ConfigDict(extra="allow")

    schema_version: Literal[1] = 1
    event_id: str
    run_id: str
    machine_id: str = Field(min_length=1, max_length=128)
    seq: int = Field(ge=1)
    type: Literal[
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
    occurred_at: datetime
    payload: dict[str, Any]


class RunManifest(BaseModel):
    run_id: str
    machine_id: str
    title: str
    argv: list[str]
    cwd: str
    progress_mode: ProgressMode = ProgressMode.INDETERMINATE
    pattern: str | None = None
    match: str | None = None
    total: float | None = None
    unit: str | None = None
    share_log_tail: int = Field(default=0, ge=0, le=100)
    socket_path: str
    socket_token: str
    handoff_path: str
    handoff_nonce: str
    handoff_timeout_seconds: float = Field(default=10.0, ge=1, le=60)
    log_path: str
    result_path: str
    cancel_grace_seconds: float = Field(default=3.0, ge=0.05, le=60)

    @field_validator("argv")
    @classmethod
    def command_required(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("a command is required")
        if "\x00" in "".join(value):
            raise ValueError("command contains a NUL byte")
        return value

    def write_securely(self, path: Path) -> None:
        path.write_text(self.model_dump_json(indent=2), encoding="utf-8")
        path.chmod(0o600)


class WorkerResult(BaseModel):
    run_id: str
    status: ExecutionStatus
    exit_code: int
    started_at: datetime | None
    ended_at: datetime
    termination_reason: str | None = None
