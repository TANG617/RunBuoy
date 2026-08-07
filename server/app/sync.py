from __future__ import annotations

import base64
import json
from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import HTTPException, status
from sqlalchemy import update
from sqlalchemy.orm import Session

from .models import Workspace

CursorKind = Literal["runs", "notifications"]


def bump_workspace_revision(session: Session, workspace_id: str) -> int:
    """Atomically advance one workspace's durable, monotonic sync revision."""
    revision = session.scalar(
        update(Workspace)
        .where(Workspace.id == workspace_id)
        .values(revision=Workspace.revision + 1)
        .returning(Workspace.revision)
    )
    if revision is None:
        raise RuntimeError(f"workspace does not exist: {workspace_id}")
    return revision


def encode_history_cursor(
    kind: CursorKind,
    sort_time: datetime,
    item_id: str,
    machine_id: str | None,
) -> str:
    if sort_time.tzinfo is None:
        sort_time = sort_time.replace(tzinfo=UTC)
    payload = {
        "v": 1,
        "kind": kind,
        "time": sort_time.isoformat(),
        "id": item_id,
        "machine_id": machine_id,
    }
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_history_cursor(
    cursor: str,
    *,
    expected_kind: CursorKind,
    machine_id: str | None,
) -> tuple[datetime, str]:
    try:
        padding = "=" * (-len(cursor) % 4)
        decoded = base64.b64decode(cursor + padding, altchars=b"-_", validate=True)
        payload: dict[str, Any] = json.loads(decoded)
        if set(payload) != {"v", "kind", "time", "id", "machine_id"}:
            raise ValueError("unexpected cursor fields")
        if payload["v"] != 1 or payload["kind"] != expected_kind:
            raise ValueError("cursor kind mismatch")
        if payload["machine_id"] != machine_id:
            raise ValueError("cursor filter mismatch")
        sort_time = datetime.fromisoformat(payload["time"])
        item_id = payload["id"]
        if sort_time.tzinfo is None or not isinstance(item_id, str) or not item_id:
            raise ValueError("invalid cursor values")
        return sort_time, item_id
    except (UnicodeDecodeError, ValueError, TypeError, json.JSONDecodeError) as error:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid history cursor") from error
