"""Dependency-free structured progress client for processes launched by RunBuoy."""

from __future__ import annotations

import json
import os
import socket
from typing import Any

__all__ = ["attention", "message", "phase", "progress"]
__version__ = "0.1.0"


def _emit(kind: str, **payload: Any) -> None:
    socket_path = os.environ.get("RUNBUOY_EVENT_SOCKET")
    token = os.environ.get("RUNBUOY_EVENT_TOKEN")
    if not socket_path or not token:
        raise RuntimeError("this process is not running under RunBuoy structured progress")
    request = {"token": token, "kind": kind, **payload}
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(2)
        client.connect(socket_path)
        client.sendall(json.dumps(request).encode() + b"\n")
        response = bytearray()
        while b"\n" not in response:
            chunk = client.recv(4096)
            if not chunk:
                break
            response.extend(chunk)
    result = json.loads(bytes(response).split(b"\n", 1)[0])
    if not result.get("ok"):
        raise RuntimeError(f"RunBuoy event rejected: {result.get('error', 'unknown_error')}")


def progress(
    current: float,
    total: float,
    *,
    unit: str | None = None,
    phase: str | None = None,
    message: str | None = None,
) -> None:
    _emit(
        "progress",
        current=current,
        total=total,
        unit=unit,
        phase=phase,
        message=message,
    )


def phase(value: str) -> None:
    _emit("phase", phase=value)


def message(value: str) -> None:
    _emit("message", message=value)


def attention(value: str, *, status: str = "ACTION_REQUIRED") -> None:
    _emit("attention", message=value, attention_status=status)
