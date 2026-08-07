from __future__ import annotations

import base64
import hashlib
import ipaddress
import os
from dataclasses import dataclass


def _development_fernet_key() -> str:
    """Stable local-only key; deployments must replace it."""
    digest = hashlib.sha256(b"runbuoy-development-only-encryption-key").digest()
    return base64.urlsafe_b64encode(digest).decode()


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean")


def _env_csv(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    value = os.getenv(name)
    if value is None:
        return default
    return tuple(item.strip() for item in value.split(",") if item.strip())


@dataclass(frozen=True, slots=True)
class Settings:
    deployment_environment: str = "development"
    region: str = "global"
    database_url: str = "sqlite:///./runbuoy.db"
    credential_pepper: str = "runbuoy-development-only-credential-pepper"
    token_encryption_key: str = _development_fernet_key()
    pairing_ttl_seconds: int = 300
    event_retention_hours: int = 24
    run_retention_days: int = 30
    notification_retention_days: int = 30
    push_attempt_retention_days: int = 7
    outbox_terminal_retention_days: int = 7
    pairing_retention_hours: int = 24
    audit_retention_days: int = 90
    safe_log_tail_retention_hours: int = 24
    retention_cleanup_batch_size: int = 500
    workspace_deletion_challenge_ttl_seconds: int = 300
    apns_mode: str = "mock"
    apns_environment: str = "development"
    apns_key_id: str | None = None
    apns_team_id: str | None = None
    apns_bundle_id: str = "dev.runbuoy.app"
    apns_private_key: str | None = None
    apns_private_key_path: str | None = None
    live_activity_start_delay_seconds: int = 5
    live_activity_update_interval_seconds: int = 1
    live_activity_max_per_device: int = 2
    live_activity_pending_ttl_seconds: int = 300
    outbox_max_attempts: int = 6
    max_request_body_bytes: int = 256 * 1024
    rate_limit_ip_pepper: str = "runbuoy-development-only-rate-limit-ip-pepper"
    trusted_proxy_cidrs: tuple[str, ...] = ()
    rate_limit_fail_open: bool = False
    rate_limit_bucket_retention_seconds: int = 3600
    rate_limit_device_bootstrap_per_hour: int = 20
    rate_limit_pairing_create_per_hour: int = 30
    rate_limit_pairing_poll_per_minute: int = 120
    rate_limit_run_upsert_per_minute: int = 120
    rate_limit_event_batch_per_minute: int = 240
    rate_limit_notification_per_minute: int = 60
    rate_limit_webhook_event_per_minute: int = 240
    max_machines_per_workspace: int = 25
    max_active_runs_per_machine: int = 100
    max_pending_pairings_per_ip: int = 10
    max_webhooks_per_workspace: int = 50
    max_notifications_per_workspace_day: int = 1000
    max_events_per_batch: int = 100
    worker_heartbeat_max_age_seconds: int = 90
    worker_heartbeat_interval_seconds: int = 15
    worker_heartbeat_required: bool = True

    @classmethod
    def from_env(cls) -> Settings:
        defaults = cls()
        return cls(
            deployment_environment=os.getenv(
                "RUNBUOY_ENVIRONMENT", defaults.deployment_environment
            ),
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
            run_retention_days=int(
                os.getenv("RUN_RETENTION_DAYS", str(defaults.run_retention_days))
            ),
            notification_retention_days=int(
                os.getenv(
                    "NOTIFICATION_RETENTION_DAYS",
                    str(defaults.notification_retention_days),
                )
            ),
            push_attempt_retention_days=int(
                os.getenv(
                    "PUSH_ATTEMPT_RETENTION_DAYS",
                    str(defaults.push_attempt_retention_days),
                )
            ),
            outbox_terminal_retention_days=int(
                os.getenv(
                    "OUTBOX_TERMINAL_RETENTION_DAYS",
                    str(defaults.outbox_terminal_retention_days),
                )
            ),
            pairing_retention_hours=int(
                os.getenv("PAIRING_RETENTION_HOURS", str(defaults.pairing_retention_hours))
            ),
            audit_retention_days=int(
                os.getenv("AUDIT_RETENTION_DAYS", str(defaults.audit_retention_days))
            ),
            safe_log_tail_retention_hours=int(
                os.getenv(
                    "SAFE_LOG_TAIL_RETENTION_HOURS",
                    str(defaults.safe_log_tail_retention_hours),
                )
            ),
            retention_cleanup_batch_size=int(
                os.getenv(
                    "RETENTION_CLEANUP_BATCH_SIZE",
                    str(defaults.retention_cleanup_batch_size),
                )
            ),
            workspace_deletion_challenge_ttl_seconds=int(
                os.getenv(
                    "WORKSPACE_DELETION_CHALLENGE_TTL_SECONDS",
                    str(defaults.workspace_deletion_challenge_ttl_seconds),
                )
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
            max_request_body_bytes=int(
                os.getenv("MAX_REQUEST_BODY_BYTES", str(defaults.max_request_body_bytes))
            ),
            rate_limit_ip_pepper=os.getenv("RATE_LIMIT_IP_PEPPER", defaults.rate_limit_ip_pepper),
            trusted_proxy_cidrs=_env_csv("TRUSTED_PROXY_CIDRS", defaults.trusted_proxy_cidrs),
            rate_limit_fail_open=_env_bool("RATE_LIMIT_FAIL_OPEN", defaults.rate_limit_fail_open),
            rate_limit_bucket_retention_seconds=int(
                os.getenv(
                    "RATE_LIMIT_BUCKET_RETENTION_SECONDS",
                    str(defaults.rate_limit_bucket_retention_seconds),
                )
            ),
            rate_limit_device_bootstrap_per_hour=int(
                os.getenv(
                    "RATE_LIMIT_DEVICE_BOOTSTRAP_PER_HOUR",
                    str(defaults.rate_limit_device_bootstrap_per_hour),
                )
            ),
            rate_limit_pairing_create_per_hour=int(
                os.getenv(
                    "RATE_LIMIT_PAIRING_CREATE_PER_HOUR",
                    str(defaults.rate_limit_pairing_create_per_hour),
                )
            ),
            rate_limit_pairing_poll_per_minute=int(
                os.getenv(
                    "RATE_LIMIT_PAIRING_POLL_PER_MINUTE",
                    str(defaults.rate_limit_pairing_poll_per_minute),
                )
            ),
            rate_limit_run_upsert_per_minute=int(
                os.getenv(
                    "RATE_LIMIT_RUN_UPSERT_PER_MINUTE",
                    str(defaults.rate_limit_run_upsert_per_minute),
                )
            ),
            rate_limit_event_batch_per_minute=int(
                os.getenv(
                    "RATE_LIMIT_EVENT_BATCH_PER_MINUTE",
                    str(defaults.rate_limit_event_batch_per_minute),
                )
            ),
            rate_limit_notification_per_minute=int(
                os.getenv(
                    "RATE_LIMIT_NOTIFICATION_PER_MINUTE",
                    str(defaults.rate_limit_notification_per_minute),
                )
            ),
            rate_limit_webhook_event_per_minute=int(
                os.getenv(
                    "RATE_LIMIT_WEBHOOK_EVENT_PER_MINUTE",
                    str(defaults.rate_limit_webhook_event_per_minute),
                )
            ),
            max_machines_per_workspace=int(
                os.getenv("MAX_MACHINES_PER_WORKSPACE", str(defaults.max_machines_per_workspace))
            ),
            max_active_runs_per_machine=int(
                os.getenv(
                    "MAX_ACTIVE_RUNS_PER_MACHINE",
                    str(defaults.max_active_runs_per_machine),
                )
            ),
            max_pending_pairings_per_ip=int(
                os.getenv(
                    "MAX_PENDING_PAIRINGS_PER_IP",
                    str(defaults.max_pending_pairings_per_ip),
                )
            ),
            max_webhooks_per_workspace=int(
                os.getenv(
                    "MAX_WEBHOOKS_PER_WORKSPACE",
                    str(defaults.max_webhooks_per_workspace),
                )
            ),
            max_notifications_per_workspace_day=int(
                os.getenv(
                    "MAX_NOTIFICATIONS_PER_WORKSPACE_DAY",
                    str(defaults.max_notifications_per_workspace_day),
                )
            ),
            max_events_per_batch=int(
                os.getenv("MAX_EVENTS_PER_BATCH", str(defaults.max_events_per_batch))
            ),
            worker_heartbeat_max_age_seconds=int(
                os.getenv(
                    "WORKER_HEARTBEAT_MAX_AGE_SECONDS",
                    str(defaults.worker_heartbeat_max_age_seconds),
                )
            ),
            worker_heartbeat_interval_seconds=int(
                os.getenv(
                    "WORKER_HEARTBEAT_INTERVAL_SECONDS",
                    str(defaults.worker_heartbeat_interval_seconds),
                )
            ),
            worker_heartbeat_required=_env_bool(
                "WORKER_HEARTBEAT_REQUIRED", defaults.worker_heartbeat_required
            ),
        )

    def configuration_errors(self) -> list[str]:
        errors: list[str] = []
        if self.deployment_environment not in {"development", "test", "production"}:
            errors.append("RUNBUOY_ENVIRONMENT")
        if self.region not in {"global", "cn"}:
            errors.append("RUNBUOY_REGION")
        if not self.database_url:
            errors.append("DATABASE_URL")
        if self.worker_heartbeat_max_age_seconds <= 0:
            errors.append("WORKER_HEARTBEAT_MAX_AGE_SECONDS")
        if self.worker_heartbeat_interval_seconds <= 0:
            errors.append("WORKER_HEARTBEAT_INTERVAL_SECONDS")
        if self.worker_heartbeat_interval_seconds >= self.worker_heartbeat_max_age_seconds:
            errors.append("WORKER_HEARTBEAT_INTERVAL_SECONDS")
        if self.apns_mode not in {"mock", "production"}:
            errors.append("APNS_MODE")
        if self.apns_environment not in {"development", "production"}:
            errors.append("APNS_ENVIRONMENT")
        positive_retention_values = {
            "EVENT_RETENTION_HOURS": self.event_retention_hours,
            "RUN_RETENTION_DAYS": self.run_retention_days,
            "NOTIFICATION_RETENTION_DAYS": self.notification_retention_days,
            "PUSH_ATTEMPT_RETENTION_DAYS": self.push_attempt_retention_days,
            "OUTBOX_TERMINAL_RETENTION_DAYS": self.outbox_terminal_retention_days,
            "PAIRING_RETENTION_HOURS": self.pairing_retention_hours,
            "AUDIT_RETENTION_DAYS": self.audit_retention_days,
            "SAFE_LOG_TAIL_RETENTION_HOURS": self.safe_log_tail_retention_hours,
            "RETENTION_CLEANUP_BATCH_SIZE": self.retention_cleanup_batch_size,
            "WORKSPACE_DELETION_CHALLENGE_TTL_SECONDS": (
                self.workspace_deletion_challenge_ttl_seconds
            ),
        }
        errors.extend(name for name, value in positive_retention_values.items() if value <= 0)
        positive_limits = {
            "MAX_REQUEST_BODY_BYTES": self.max_request_body_bytes,
            "RATE_LIMIT_BUCKET_RETENTION_SECONDS": self.rate_limit_bucket_retention_seconds,
            "RATE_LIMIT_DEVICE_BOOTSTRAP_PER_HOUR": self.rate_limit_device_bootstrap_per_hour,
            "RATE_LIMIT_PAIRING_CREATE_PER_HOUR": self.rate_limit_pairing_create_per_hour,
            "RATE_LIMIT_PAIRING_POLL_PER_MINUTE": self.rate_limit_pairing_poll_per_minute,
            "RATE_LIMIT_RUN_UPSERT_PER_MINUTE": self.rate_limit_run_upsert_per_minute,
            "RATE_LIMIT_EVENT_BATCH_PER_MINUTE": self.rate_limit_event_batch_per_minute,
            "RATE_LIMIT_NOTIFICATION_PER_MINUTE": self.rate_limit_notification_per_minute,
            "RATE_LIMIT_WEBHOOK_EVENT_PER_MINUTE": self.rate_limit_webhook_event_per_minute,
            "MAX_MACHINES_PER_WORKSPACE": self.max_machines_per_workspace,
            "MAX_ACTIVE_RUNS_PER_MACHINE": self.max_active_runs_per_machine,
            "MAX_PENDING_PAIRINGS_PER_IP": self.max_pending_pairings_per_ip,
            "MAX_WEBHOOKS_PER_WORKSPACE": self.max_webhooks_per_workspace,
            "MAX_NOTIFICATIONS_PER_WORKSPACE_DAY": self.max_notifications_per_workspace_day,
            "MAX_EVENTS_PER_BATCH": self.max_events_per_batch,
        }
        errors.extend(name for name, value in positive_limits.items() if value <= 0)
        if not self.rate_limit_ip_pepper:
            errors.append("RATE_LIMIT_IP_PEPPER")
        for network in self.trusted_proxy_cidrs:
            try:
                ipaddress.ip_network(network, strict=False)
            except ValueError:
                errors.append("TRUSTED_PROXY_CIDRS")
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
            errors.extend(missing)
        if self.deployment_environment == "production":
            if not self.database_url.startswith("postgresql"):
                errors.append("DATABASE_URL")
            if (
                len(self.credential_pepper) < 32
                or self.credential_pepper.startswith("runbuoy-development-only")
                or self.credential_pepper.startswith("replace-with-")
            ):
                errors.append("CREDENTIAL_PEPPER")
            if self.token_encryption_key in {
                _development_fernet_key(),
                "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
            }:
                errors.append("TOKEN_ENCRYPTION_KEY")
        return sorted(set(errors))

    def validate(self) -> None:
        errors = self.configuration_errors()
        if errors:
            raise ValueError(f"invalid or missing configuration: {', '.join(errors)}")
