from __future__ import annotations

import base64
import hashlib
import os
from dataclasses import dataclass


def _development_fernet_key() -> str:
    """Stable local-only key; deployments must replace it."""
    digest = hashlib.sha256(b"runbuoy-development-only-encryption-key").digest()
    return base64.urlsafe_b64encode(digest).decode()


@dataclass(frozen=True, slots=True)
class Settings:
    region: str = "global"
    database_url: str = "sqlite:///./runbuoy.db"
    credential_pepper: str = "runbuoy-development-only-credential-pepper"
    token_encryption_key: str = _development_fernet_key()
    pairing_ttl_seconds: int = 300
    event_retention_hours: int = 24
    apns_mode: str = "mock"
    apns_environment: str = "development"
    apns_key_id: str | None = None
    apns_team_id: str | None = None
    apns_bundle_id: str = "dev.runbuoy.app"
    apns_private_key: str | None = None
    apns_private_key_path: str | None = None
    live_activity_start_delay_seconds: int = 5
    live_activity_update_interval_seconds: int = 3
    live_activity_max_per_device: int = 2
    live_activity_pending_ttl_seconds: int = 300
    outbox_max_attempts: int = 6

    @classmethod
    def from_env(cls) -> Settings:
        defaults = cls()
        return cls(
            region=os.getenv("RUNBUOY_REGION", defaults.region),
            database_url=os.getenv("DATABASE_URL", defaults.database_url),
            credential_pepper=os.getenv("CREDENTIAL_PEPPER", defaults.credential_pepper),
            token_encryption_key=os.getenv("TOKEN_ENCRYPTION_KEY", _development_fernet_key()),
            pairing_ttl_seconds=int(
                os.getenv("PAIRING_TTL_SECONDS", str(defaults.pairing_ttl_seconds))
            ),
            event_retention_hours=int(
                os.getenv("EVENT_RETENTION_HOURS", str(defaults.event_retention_hours))
            ),
            apns_mode=os.getenv("APNS_MODE", defaults.apns_mode),
            apns_environment=os.getenv("APNS_ENVIRONMENT", defaults.apns_environment),
            apns_key_id=os.getenv("APNS_KEY_ID"),
            apns_team_id=os.getenv("APNS_TEAM_ID"),
            apns_bundle_id=os.getenv("APNS_BUNDLE_ID", defaults.apns_bundle_id),
            apns_private_key=os.getenv("APNS_PRIVATE_KEY"),
            apns_private_key_path=os.getenv("APNS_PRIVATE_KEY_PATH"),
            live_activity_start_delay_seconds=int(
                os.getenv(
                    "LIVE_ACTIVITY_START_DELAY_SECONDS",
                    str(defaults.live_activity_start_delay_seconds),
                )
            ),
            live_activity_update_interval_seconds=int(
                os.getenv(
                    "LIVE_ACTIVITY_UPDATE_INTERVAL_SECONDS",
                    str(defaults.live_activity_update_interval_seconds),
                )
            ),
            live_activity_max_per_device=int(
                os.getenv(
                    "LIVE_ACTIVITY_MAX_PER_DEVICE",
                    str(defaults.live_activity_max_per_device),
                )
            ),
            live_activity_pending_ttl_seconds=int(
                os.getenv(
                    "LIVE_ACTIVITY_PENDING_TTL_SECONDS",
                    str(defaults.live_activity_pending_ttl_seconds),
                )
            ),
            outbox_max_attempts=int(
                os.getenv("OUTBOX_MAX_ATTEMPTS", str(defaults.outbox_max_attempts))
            ),
        )

    def validate(self) -> None:
        if self.region not in {"global", "cn"}:
            raise ValueError("RUNBUOY_REGION must be global or cn")
        if self.apns_mode not in {"mock", "production"}:
            raise ValueError("APNS_MODE must be mock or production")
        if self.apns_environment not in {"development", "production"}:
            raise ValueError("APNS_ENVIRONMENT must be development or production")
        if self.apns_mode == "production":
            missing = [
                name
                for name, value in {
                    "APNS_KEY_ID": self.apns_key_id,
                    "APNS_TEAM_ID": self.apns_team_id,
                    "APNS_BUNDLE_ID": self.apns_bundle_id,
                }.items()
                if not value
            ]
            if not self.apns_private_key and not self.apns_private_key_path:
                missing.append("APNS_PRIVATE_KEY or APNS_PRIVATE_KEY_PATH")
            if missing:
                raise ValueError(f"production APNs configuration missing: {', '.join(missing)}")
