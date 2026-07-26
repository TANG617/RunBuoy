from __future__ import annotations

import platform
import time
from collections.abc import Callable
from typing import Any
from urllib.parse import quote, urlencode

from runbuoy import __version__
from runbuoy.config import Config, CredentialStore
from runbuoy.networking.client import RemoteClient


def public_pairing_fields(value: dict[str, Any]) -> dict[str, Any]:
    """Remove every secret/credential/token-shaped field before user output."""
    return {
        key: item
        for key, item in value.items()
        if not any(part in key.lower() for part in ("secret", "credential", "token"))
    }


def pair_machine(
    config: Config,
    credentials: CredentialStore,
    *,
    wait: bool = True,
    timeout_seconds: float = 300,
    on_created: Callable[[dict[str, Any], str], None] | None = None,
) -> tuple[dict[str, Any], str]:
    client = RemoteClient(config, credentials)
    try:
        created = client.create_pairing(
            {
                "display_name": config.machine_name,
                "platform": platform.system().lower(),
                "architecture": platform.machine(),
                "cli_version": __version__,
            }
        )
        session_id = str(
            created.get("pairing_session_id") or created.get("session_id") or created.get("id")
        )
        exchange_secret = str(created.get("exchange_secret", ""))
        challenge = str(created.get("challenge") or created.get("short_code") or "")
        if not session_id or session_id == "None" or not exchange_secret:
            raise RuntimeError("pairing response is missing session ID or exchange secret")
        query = urlencode(
            {
                "challenge": challenge,
                "machine": config.machine_name,
                "platform": platform.system().lower(),
            }
        )
        qr_value = f"runbuoy://pair/{quote(session_id, safe='')}?{query}"
        safe_created = public_pairing_fields(created)
        if on_created is not None:
            on_created(safe_created, qr_value)
        if not wait:
            return safe_created, qr_value
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            status = client.pairing_status(session_id, exchange_secret)
            state = str(status.get("status", "")).lower()
            if state in {"claimed", "ready", "completed"} or status.get("claimed_at"):
                exchanged = client.exchange_pairing(session_id, exchange_secret)
                credential = exchanged.get("machine_credential") or exchanged.get("credential")
                if not credential:
                    raise RuntimeError("pairing exchange did not return a machine credential")
                credentials.set("machine_credential", str(credential))
                merged = {**created, **exchanged, "status": "paired"}
                return merged, qr_value
            if state in {"expired", "revoked"}:
                raise RuntimeError(f"pairing session {state}")
            time.sleep(2)
        raise TimeoutError("pairing session timed out")
    finally:
        client.close()
