from __future__ import annotations

import re
from pathlib import Path

from runbuoy.security.redaction import redact

SAFE_PART_RE = re.compile(r"[^A-Za-z0-9._+\- ]+")
INTERPRETERS = {"python", "python3", "ruby", "node", "deno", "bun", "bash", "sh", "zsh"}


def _safe_part(value: str, fallback: str) -> str:
    base = Path(value).name
    cleaned = SAFE_PART_RE.sub("", redact(base)).strip(" .-_")
    return (cleaned or fallback)[:80]


def safe_title(argv: list[str], explicit: str | None = None) -> str:
    if explicit is not None:
        title = redact(explicit).replace("\n", " ").replace("\r", " ").strip()
        title = re.sub(r"\s+", " ", title)[:120]
        if not title:
            raise ValueError("title cannot be empty")
        return title
    if not argv:
        return "Command"
    executable = _safe_part(argv[0], "command")
    lowered = executable.lower()
    if lowered in INTERPRETERS and len(argv) > 1 and not argv[1].startswith("-"):
        return f"{executable} · {_safe_part(argv[1], 'script')}"
    if lowered == "cargo" and len(argv) > 1:
        return f"cargo · {_safe_part(argv[1], 'command')}"
    if lowered == "docker" and len(argv) > 1:
        return f"docker · {_safe_part(argv[1], 'command')}"
    return executable
