"""Identifiers used by the local execution plane."""

from __future__ import annotations

import os
import time
import uuid


def uuid7() -> uuid.UUID:
    """Return a time-ordered RFC 9562 UUIDv7 without an external dependency."""
    timestamp_ms = time.time_ns() // 1_000_000
    random_bytes = bytearray(os.urandom(10))
    value = (timestamp_ms & ((1 << 48) - 1)) << 80
    value |= 0x7 << 76
    value |= int.from_bytes(random_bytes, "big") & ((1 << 76) - 1)
    value &= ~(0b11 << 62)
    value |= 0b10 << 62
    return uuid.UUID(int=value)
