from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import httpx
import jwt

from .config import Settings


@dataclass(frozen=True, slots=True)
class APNsRequest:
    token: str
    payload: dict[str, Any]
    headers: dict[str, str]


@dataclass(frozen=True, slots=True)
class APNsResult:
    status_code: int
    apns_id: str | None = None
    reason: str | None = None

    @property
    def accepted(self) -> bool:
        return 200 <= self.status_code < 300

    @property
    def invalid_token(self) -> bool:
        return self.status_code == 410 or self.reason in {
            "BadDeviceToken",
            "DeviceTokenNotForTopic",
            "ExpiredToken",
            "Unregistered",
        }

    @property
    def retryable(self) -> bool:
        return self.status_code in {429, 500, 503}


class APNsProvider(Protocol):
    def send(self, request: APNsRequest) -> APNsResult: ...

    def close(self) -> None: ...


class MockAPNsProvider:
    """Deterministic provider; PushAttempt rows are the durable mock send log."""

    def send(self, request: APNsRequest) -> APNsResult:
        del request
        return APNsResult(status_code=200, apns_id=str(uuid.uuid4()))

    def close(self) -> None:
        return None


class ProductionAPNsProvider:
    """HTTP/2 token-authenticated APNs provider.

    Apple sources used for the protocol facts in this module:
    - https://developer.apple.com/documentation/usernotifications/
      establishing-a-token-based-connection-to-apns
    - https://developer.apple.com/documentation/usernotifications/
      sending-notification-requests-to-apns
    - https://developer.apple.com/documentation/usernotifications/
      handling-notification-responses-from-apns

    APNs requires ES256 and rejects provider JWTs older than one hour. This
    implementation refreshes after 50 minutes, within Apple's documented
    provider-token lifetime, and reuses one HTTP/2 client.
    """

    def __init__(self, settings: Settings, client: httpx.Client | None = None) -> None:
        settings.validate()
        self.settings = settings
        self._client = client or httpx.Client(http2=True, timeout=15.0)
        self._jwt: str | None = None
        self._jwt_issued_at = 0
        if settings.apns_private_key is not None:
            self._private_key = settings.apns_private_key.replace("\\n", "\n")
        elif settings.apns_private_key_path is not None:
            self._private_key = Path(settings.apns_private_key_path).read_text()
        else:  # guarded by validate
            raise ValueError("APNs private key is required")

    @property
    def endpoint(self) -> str:
        if self.settings.apns_environment == "production":
            return "https://api.push.apple.com"
        return "https://api.development.push.apple.com"

    def _provider_token(self) -> str:
        now = int(time.time())
        if self._jwt is None or now - self._jwt_issued_at >= 50 * 60:
            self._jwt_issued_at = now
            self._jwt = jwt.encode(
                {"iss": self.settings.apns_team_id, "iat": now},
                self._private_key,
                algorithm="ES256",
                headers={"kid": self.settings.apns_key_id},
            )
        return self._jwt

    def send(self, request: APNsRequest) -> APNsResult:
        headers = dict(request.headers)
        headers["authorization"] = f"bearer {self._provider_token()}"
        response = self._client.post(
            f"{self.endpoint}/3/device/{request.token}",
            headers=headers,
            content=json.dumps(request.payload, separators=(",", ":")),
        )
        reason: str | None = None
        if response.content:
            try:
                value = response.json()
                if isinstance(value, dict):
                    reason_value = value.get("reason")
                    reason = str(reason_value) if reason_value is not None else None
            except ValueError:
                reason = "InvalidAPNsResponse"
        return APNsResult(
            status_code=response.status_code,
            apns_id=response.headers.get("apns-id"),
            reason=reason,
        )

    def close(self) -> None:
        self._client.close()


def provider_for(settings: Settings) -> APNsProvider:
    if settings.apns_mode == "mock":
        return MockAPNsProvider()
    return ProductionAPNsProvider(settings)


def normal_notification_headers(settings: Settings, priority: int) -> dict[str, str]:
    return {
        "apns-push-type": "alert",
        "apns-topic": settings.apns_bundle_id,
        "apns-priority": str(priority),
        "apns-expiration": "0",
    }


def live_activity_headers(
    settings: Settings, priority: int, *, collapse_id: str | None = None
) -> dict[str, str]:
    # Apple requires the liveactivity push type and the bundle topic suffix.
    headers = {
        "apns-push-type": "liveactivity",
        "apns-topic": f"{settings.apns_bundle_id}.push-type.liveactivity",
        "apns-priority": str(priority),
        "apns-expiration": "0",
    }
    if collapse_id is not None:
        headers["apns-collapse-id"] = collapse_id[:64]
    return headers
