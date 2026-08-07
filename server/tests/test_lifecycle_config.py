from __future__ import annotations

import pytest

from app.config import Settings


def test_lifecycle_retention_settings_load_from_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = {
        "EVENT_RETENTION_HOURS": "12",
        "RUN_RETENTION_DAYS": "31",
        "NOTIFICATION_RETENTION_DAYS": "32",
        "PUSH_ATTEMPT_RETENTION_DAYS": "8",
        "OUTBOX_TERMINAL_RETENTION_DAYS": "9",
        "PAIRING_RETENTION_HOURS": "25",
        "AUDIT_RETENTION_DAYS": "91",
        "SAFE_LOG_TAIL_RETENTION_HOURS": "23",
        "RETENTION_CLEANUP_BATCH_SIZE": "123",
        "WORKSPACE_DELETION_CHALLENGE_TTL_SECONDS": "240",
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)

    settings = Settings.from_env()

    assert settings.event_retention_hours == 12
    assert settings.run_retention_days == 31
    assert settings.notification_retention_days == 32
    assert settings.push_attempt_retention_days == 8
    assert settings.outbox_terminal_retention_days == 9
    assert settings.pairing_retention_hours == 25
    assert settings.audit_retention_days == 91
    assert settings.safe_log_tail_retention_hours == 23
    assert settings.retention_cleanup_batch_size == 123
    assert settings.workspace_deletion_challenge_ttl_seconds == 240
    settings.validate()


def test_lifecycle_retention_settings_must_be_positive() -> None:
    with pytest.raises(ValueError, match="RUN_RETENTION_DAYS"):
        Settings(run_retention_days=0).validate()
