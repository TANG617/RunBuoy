from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import Settings
from .database import get_session
from .models import DeviceCredential, MachineCredential
from .security import token_hash

DEVICE_SCOPES = frozenset(
    {
        "runs:read",
        "machines:read",
        "notifications:read",
        "devices:register-token",
        "live-activities:register-token",
        "pairing:claim",
        "preferences:write",
        "subscriptions:delete",
    }
)
MACHINE_SCOPES = frozenset(
    {
        "runs:create",
        "runs:update",
        "events:write",
        "notifications:send",
        "hooks:manage",
        "machines:update",
        "pairing:poll",
    }
)


@dataclass(frozen=True, slots=True)
class Principal:
    kind: str
    subject_id: str
    workspace_id: str
    scopes: frozenset[str]


bearer = HTTPBearer(auto_error=False)


def _settings(request: Request) -> Settings:
    return request.app.state.settings


def authenticate(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    session: Session = Depends(get_session),
) -> Principal:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer credential")
    digest = token_hash(credentials.credentials, _settings(request).credential_pepper)

    device_credential = session.scalar(
        select(DeviceCredential).where(
            DeviceCredential.token_hash == digest,
            DeviceCredential.revoked_at.is_(None),
        )
    )
    if device_credential is not None and device_credential.device.revoked_at is None:
        return Principal(
            "device",
            device_credential.device_id,
            device_credential.device.workspace_id,
            frozenset(device_credential.scopes.split()),
        )

    machine_credential = session.scalar(
        select(MachineCredential).where(
            MachineCredential.token_hash == digest,
            MachineCredential.revoked_at.is_(None),
        )
    )
    if machine_credential is not None and machine_credential.machine.revoked_at is None:
        return Principal(
            "machine",
            machine_credential.machine_id,
            machine_credential.machine.workspace_id,
            frozenset(machine_credential.scopes.split()),
        )
    raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid bearer credential")


def require_scope(scope: str) -> Callable[[Principal], Principal]:
    def dependency(principal: Principal = Depends(authenticate)) -> Principal:
        if scope not in principal.scopes:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"missing scope: {scope}")
        return principal

    return dependency
