from __future__ import annotations

import json
import os
import platform
import secrets
from contextlib import suppress
from enum import StrEnum
from typing import Any, cast

from pydantic import BaseModel, Field, HttpUrl

from runbuoy.ids import uuid7
from runbuoy.paths import AppPaths


class RunBuoyRegion(StrEnum):
    GLOBAL = "global"
    CHINA = "cn"

    @property
    def server_url(self) -> str:
        if self is RunBuoyRegion.CHINA:
            return "https://api-cn.runbuoy.cloud"
        return "https://api.runbuoy.cloud"


class Config(BaseModel):
    region: RunBuoyRegion = RunBuoyRegion.GLOBAL
    server_url: HttpUrl = Field(default=HttpUrl("https://api.runbuoy.cloud"))
    machine_id: str | None = None
    machine_name: str = Field(default_factory=platform.node)
    upload_interval_seconds: float = Field(default=1.0, ge=0.1, le=60)
    batch_size: int = Field(default=20, ge=1, le=100)
    cancel_grace_seconds: float = Field(default=3.0, ge=0.05, le=60)


def load_config(paths: AppPaths) -> Config:
    paths.ensure()
    if not paths.config_file.exists():
        return Config()
    return Config.model_validate_json(paths.config_file.read_text(encoding="utf-8"))


def save_config(paths: AppPaths, config: Config) -> None:
    paths.ensure()
    paths.config_file.write_text(config.model_dump_json(indent=2), encoding="utf-8")
    paths.config_file.chmod(0o600)


def ensure_machine_identity(paths: AppPaths, config: Config) -> Config:
    """Persist one stable ID before pairing or creating local Runs."""
    if config.machine_id is not None:
        return config
    updated = config.model_copy(update={"machine_id": f"machine_{uuid7().hex}"})
    save_config(paths, updated)
    return updated


class CredentialStore:
    """Keyring-backed credentials with a mode-0600 fallback."""

    service = "dev.runbuoy.cli"

    def __init__(self, paths: AppPaths) -> None:
        self.paths = paths

    def _keyring(self) -> Any | None:
        if os.environ.get("RUNBUOY_DISABLE_KEYRING") == "1":
            return None
        try:
            import keyring

            backend = keyring.get_keyring()
            if getattr(backend, "priority", 0) <= 0:
                return None
            return keyring
        except Exception:
            return None

    def get(self, name: str) -> str | None:
        backend = self._keyring()
        if backend is not None:
            try:
                return cast(str | None, backend.get_password(self.service, name))
            except Exception:
                pass
        return self._read_fallback().get(name)

    def set(self, name: str, value: str) -> None:
        backend = self._keyring()
        if backend is not None:
            try:
                backend.set_password(self.service, name, value)
                return
            except Exception:
                pass
        values = self._read_fallback()
        values[name] = value
        self._write_fallback(values)

    def delete(self, name: str) -> None:
        backend = self._keyring()
        if backend is not None:
            with suppress(Exception):
                backend.delete_password(self.service, name)
        values = self._read_fallback()
        values.pop(name, None)
        self._write_fallback(values)

    def _read_fallback(self) -> dict[str, str]:
        path = self.paths.credential_file
        if not path.exists():
            return {}
        if path.stat().st_mode & 0o077:
            raise PermissionError(f"credential file permissions are too broad: {path}")
        raw = json.loads(path.read_text(encoding="utf-8"))
        return {str(key): str(value) for key, value in raw.items()}

    def _write_fallback(self, values: dict[str, str]) -> None:
        self.paths.ensure()
        path = self.paths.credential_file
        path.write_text(json.dumps(values), encoding="utf-8")
        path.chmod(0o600)


def ephemeral_token() -> str:
    return secrets.token_urlsafe(32)
