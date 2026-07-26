from __future__ import annotations

import uuid

from app.security import new_id, uuid7


def test_uuid7_is_monotonic_and_rfc_compliant() -> None:
    values = [uuid7() for _ in range(1_000)]
    assert values == sorted(values)
    assert all(value.version == 7 and value.variant == uuid.RFC_4122 for value in values)
    prefixed = new_id("dev")
    assert prefixed.startswith("dev_")
    assert uuid.UUID(hex=prefixed.removeprefix("dev_")).version == 7
