from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

ANSI_RE = re.compile(r"(?:\x1B[@-_][0-?]*[ -/]*[@-~])")
SECRET_PATTERNS = (
    re.compile(r"(?i)\b(bearer\s+)[A-Za-z0-9._~+/=-]+"),
    re.compile(
        r"(?i)\b(api[_-]?key|token|secret|password|passwd|authorization)"
        r"(\s*[:=]\s*)[^\s,;]+"
    ),
    re.compile(r"\b(sk-(?:proj-)?[A-Za-z0-9_-]{8,})\b"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S),
)
FORBIDDEN_REMOTE_KEYS = frozenset(
    {
        "argv",
        "command",
        "cwd",
        "env",
        "environment",
        "stdout",
        "stderr",
        "terminal",
        "screen",
        "stdin",
        "socket_token",
        "exchange_secret",
        "credential",
        "api_key",
    }
)


def strip_ansi(value: str) -> str:
    return ANSI_RE.sub("", value)


def redact(value: str) -> str:
    result = strip_ansi(value)
    for pattern in SECRET_PATTERNS:
        if pattern.groups >= 2:
            result = pattern.sub(r"\1\2[REDACTED]", result)
        elif pattern.groups == 1:
            result = pattern.sub(r"\1[REDACTED]", result)
        else:
            result = pattern.sub("[REDACTED]", result)
    return result


def safe_message(value: str | None, max_length: int = 500) -> str | None:
    if value is None:
        return None
    cleaned = redact(value).replace("\x00", "")
    return cleaned[:max_length]


def assert_safe_remote_payload(value: Any, path: tuple[str, ...] = ()) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            normalized = str(key).lower()
            if normalized in FORBIDDEN_REMOTE_KEYS or normalized.endswith("_token"):
                dotted = ".".join((*path, str(key)))
                raise ValueError(f"forbidden remote field: {dotted}")
            assert_safe_remote_payload(item, (*path, str(key)))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            assert_safe_remote_payload(item, (*path, str(index)))
