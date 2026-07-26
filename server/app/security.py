from __future__ import annotations

import hashlib
import hmac
import secrets
import threading
import time
import uuid
from datetime import UTC, datetime

from cryptography.fernet import Fernet, InvalidToken

from .config import Settings

_uuid7_lock = threading.Lock()
_uuid7_last_ms = -1
_uuid7_last_random = -1


def uuid7() -> uuid.UUID:
    """Return a monotonic RFC 9562 UUIDv7 without an external dependency."""
    global _uuid7_last_ms, _uuid7_last_random
    with _uuid7_lock:
        timestamp_ms = max(time.time_ns() // 1_000_000, _uuid7_last_ms)
        if timestamp_ms == _uuid7_last_ms:
            random_value = _uuid7_last_random + 1
            if random_value >= 1 << 74:
                timestamp_ms += 1
                random_value = secrets.randbits(74)
        else:
            random_value = secrets.randbits(74)
        _uuid7_last_ms = timestamp_ms
        _uuid7_last_random = random_value

    random_a = random_value >> 62
    random_b = random_value & ((1 << 62) - 1)
    value = (timestamp_ms & ((1 << 48) - 1)) << 80
    value |= 0x7 << 76
    value |= random_a << 64
    value |= 0b10 << 62
    value |= random_b
    return uuid.UUID(int=value)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid7().hex}"


def new_bearer_token(prefix: str) -> str:
    return f"{prefix}_{secrets.token_urlsafe(32)}"


def token_hash(token: str, pepper: str) -> str:
    return hmac.new(pepper.encode(), token.encode(), hashlib.sha256).hexdigest()


def token_matches(token: str, expected_hash: str, pepper: str) -> bool:
    return hmac.compare_digest(token_hash(token, pepper), expected_hash)


class TokenCipher:
    def __init__(self, key: str) -> None:
        self._fernet = Fernet(key.encode())

    def encrypt(self, value: str) -> str:
        return self._fernet.encrypt(value.encode()).decode()

    def decrypt(self, value: str) -> str:
        try:
            return self._fernet.decrypt(value.encode()).decode()
        except InvalidToken as exc:
            raise ValueError("stored token cannot be decrypted") from exc


def is_expired(value: datetime, *, now: datetime | None = None) -> bool:
    current = now or datetime.now(UTC)
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value <= current


def cipher_for(settings: Settings) -> TokenCipher:
    return TokenCipher(settings.token_encryption_key)
