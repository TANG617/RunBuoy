from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from fastapi import HTTPException, Request, Response, status
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .config import Settings
from .models import QuotaLock, RateLimitBucket, utcnow


@dataclass(frozen=True, slots=True)
class RateLimitResult:
    bucket: str
    limit: int
    remaining: int
    reset_epoch: int
    retry_after: int


def anonymized_key(settings: Settings, namespace: str, value: str) -> str:
    digest = hmac.new(
        settings.rate_limit_ip_pepper.encode(),
        f"{namespace}:{value}".encode(),
        hashlib.sha256,
    ).hexdigest()
    return digest


def _trusted_networks(
    settings: Settings,
) -> tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...]:
    return tuple(
        ipaddress.ip_network(value, strict=False) for value in settings.trusted_proxy_cidrs
    )


def client_ip(request: Request, settings: Settings) -> str:
    peer_value = request.client.host if request.client is not None else "unknown"
    try:
        peer = ipaddress.ip_address(peer_value)
    except ValueError:
        return "unknown"

    trusted = _trusted_networks(settings)
    if not any(peer in network for network in trusted):
        return peer.compressed

    forwarded_header = request.headers.get("x-forwarded-for")
    if not forwarded_header:
        return peer.compressed
    try:
        forwarded = [
            ipaddress.ip_address(item.strip())
            for item in forwarded_header.split(",")
            if item.strip()
        ]
    except ValueError:
        return peer.compressed
    if not forwarded:
        return peer.compressed

    # Walk from the trusted ingress towards the original client. The first
    # address outside the configured proxy set is the client boundary.
    for address in reversed(forwarded):
        if not any(address in network for network in trusted):
            return address.compressed
    return forwarded[0].compressed


def anonymous_ip_key(request: Request, settings: Settings) -> str:
    return anonymized_key(settings, "ip", client_ip(request, settings))


def _bucket_insert(session: Session) -> Any:
    dialect = session.get_bind().dialect.name
    if dialect == "postgresql":
        return postgresql_insert(RateLimitBucket)
    if dialect == "sqlite":
        return sqlite_insert(RateLimitBucket)
    raise RuntimeError(f"rate limiting does not support database dialect: {dialect}")


def _quota_lock_insert(session: Session) -> Any:
    dialect = session.get_bind().dialect.name
    if dialect == "postgresql":
        return postgresql_insert(QuotaLock)
    if dialect == "sqlite":
        return sqlite_insert(QuotaLock)
    raise RuntimeError(f"quota locking does not support database dialect: {dialect}")


def _increment_bucket(
    session: Session,
    *,
    bucket_name: str,
    subject_key: str,
    window_start: int,
    expires_at: datetime,
    now: datetime,
) -> int:
    statement = _bucket_insert(session).values(
        bucket_name=bucket_name,
        subject_key=subject_key,
        window_start=window_start,
        request_count=1,
        expires_at=expires_at,
        updated_at=now,
    )
    statement = statement.on_conflict_do_update(
        index_elements=[
            RateLimitBucket.bucket_name,
            RateLimitBucket.subject_key,
            RateLimitBucket.window_start,
        ],
        set_={
            "request_count": RateLimitBucket.request_count + 1,
            "expires_at": expires_at,
            "updated_at": now,
        },
    ).returning(RateLimitBucket.request_count)
    return int(session.execute(statement).scalar_one())


def _rate_limit_headers(result: RateLimitResult) -> dict[str, str]:
    return {
        "X-RateLimit-Bucket": result.bucket,
        "X-RateLimit-Limit": str(result.limit),
        "X-RateLimit-Remaining": str(result.remaining),
        "X-RateLimit-Reset": str(result.reset_epoch),
    }


def enforce_rate_limit(
    session: Session,
    settings: Settings,
    response: Response,
    *,
    bucket_name: str,
    subject_key: str,
    limit: int,
    window_seconds: int,
    now: datetime | None = None,
) -> RateLimitResult | None:
    current = now or utcnow()
    epoch = int(current.timestamp())
    window_start = epoch - (epoch % window_seconds)
    reset_epoch = window_start + window_seconds
    try:
        count = _increment_bucket(
            session,
            bucket_name=bucket_name,
            subject_key=subject_key,
            window_start=window_start,
            expires_at=datetime.fromtimestamp(reset_epoch, UTC)
            + timedelta(seconds=settings.rate_limit_bucket_retention_seconds),
            now=current,
        )
        # Rate-limit accounting is intentionally independent of the business
        # transaction, including rejected or invalid requests.
        session.commit()
    except (SQLAlchemyError, RuntimeError) as exc:
        session.rollback()
        if settings.rate_limit_fail_open:
            response.headers["X-RateLimit-Policy"] = "fail-open"
            return None
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "rate_limiter_unavailable",
                "message": "request accounting is temporarily unavailable",
            },
        ) from exc

    retry_after = max(1, reset_epoch - epoch)
    result = RateLimitResult(
        bucket=bucket_name,
        limit=limit,
        remaining=max(0, limit - count),
        reset_epoch=reset_epoch,
        retry_after=retry_after,
    )
    headers = _rate_limit_headers(result)
    response.headers.update(headers)
    if count > limit:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "code": "rate_limit_exceeded",
                "bucket": bucket_name,
                "limit": limit,
                "window_seconds": window_seconds,
                "retry_after": retry_after,
            },
            headers={**headers, "Retry-After": str(retry_after)},
        )
    return result


def acquire_quota_lock(
    session: Session,
    settings: Settings,
    *,
    namespace: str,
    subject: str,
) -> None:
    now = utcnow()
    lock_key = f"{namespace}:{anonymized_key(settings, namespace, subject)}"
    statement = _quota_lock_insert(session).values(lock_key=lock_key, last_used_at=now)
    session.execute(statement.on_conflict_do_nothing(index_elements=[QuotaLock.lock_key]))
    session.flush()
    row = session.scalar(select(QuotaLock).where(QuotaLock.lock_key == lock_key).with_for_update())
    if row is None:  # pragma: no cover - protected by insert/select transaction semantics
        raise RuntimeError("quota lock disappeared")
    row.last_used_at = now


def quota_exceeded(resource: str, limit: int, scope: str) -> HTTPException:
    return HTTPException(
        status.HTTP_409_CONFLICT,
        detail={
            "code": "resource_quota_exceeded",
            "resource": resource,
            "scope": scope,
            "limit": limit,
        },
    )


def enforce_notification_daily_quota(
    session: Session,
    settings: Settings,
    *,
    workspace_id: str,
    now: datetime | None = None,
) -> None:
    current = now or utcnow()
    day_seconds = 24 * 60 * 60
    epoch = int(current.timestamp())
    window_start = epoch - (epoch % day_seconds)
    reset_epoch = window_start + day_seconds
    try:
        count = _increment_bucket(
            session,
            bucket_name="notification_daily_quota",
            subject_key=anonymized_key(settings, "workspace", workspace_id),
            window_start=window_start,
            expires_at=datetime.fromtimestamp(reset_epoch, UTC)
            + timedelta(seconds=settings.rate_limit_bucket_retention_seconds),
            now=current,
        )
    except (SQLAlchemyError, RuntimeError) as exc:
        session.rollback()
        if settings.rate_limit_fail_open:
            return
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "quota_accounting_unavailable",
                "message": "resource quota accounting is temporarily unavailable",
            },
        ) from exc
    if count > settings.max_notifications_per_workspace_day:
        retry_after = max(1, reset_epoch - epoch)
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "code": "resource_quota_exceeded",
                "resource": "notifications",
                "scope": "workspace_day",
                "limit": settings.max_notifications_per_workspace_day,
                "retry_after": retry_after,
            },
            headers={"Retry-After": str(retry_after)},
        )


def cleanup_abuse_state(
    session: Session,
    settings: Settings,
    *,
    now: datetime | None = None,
) -> dict[str, int]:
    current = now or utcnow()
    buckets = cast(
        CursorResult[Any],
        session.execute(delete(RateLimitBucket).where(RateLimitBucket.expires_at <= current)),
    ).rowcount
    lock_cutoff = current - timedelta(
        seconds=max(settings.rate_limit_bucket_retention_seconds, settings.pairing_ttl_seconds)
    )
    locks = cast(
        CursorResult[Any],
        session.execute(delete(QuotaLock).where(QuotaLock.last_used_at < lock_cutoff)),
    ).rowcount
    return {"rate_limit_buckets": int(buckets or 0), "quota_locks": int(locks or 0)}


class RequestBodyLimitMiddleware:
    """Buffer a bounded request stream before routing it to FastAPI."""

    def __init__(self, app: ASGIApp, *, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def _reject(self, send: Send) -> None:
        payload = json.dumps(
            {
                "detail": {
                    "code": "request_body_too_large",
                    "message": "request body exceeds configured limit",
                    "limit_bytes": self.max_bytes,
                }
            },
            separators=(",", ":"),
        ).encode()
        await send(
            {
                "type": "http.response.start",
                "status": status.HTTP_413_CONTENT_TOO_LARGE,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(payload)).encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": payload})

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("path") in {"/healthz", "/readyz"}:
            await self.app(scope, receive, send)
            return

        headers = {name.lower(): value for name, value in scope.get("headers", [])}
        content_length = headers.get(b"content-length")
        if content_length is not None:
            try:
                declared = int(content_length)
            except ValueError:
                declared = 0
            if declared > self.max_bytes:
                await self._reject(send)
                return

        chunks: list[bytes] = []
        total = 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            body = message.get("body", b"")
            total += len(body)
            if total > self.max_bytes:
                await self._reject(send)
                return
            chunks.append(body)
            if not message.get("more_body", False):
                break

        replayed = False

        async def replay_receive() -> Message:
            nonlocal replayed
            if replayed:
                return {"type": "http.disconnect"}
            replayed = True
            return {"type": "http.request", "body": b"".join(chunks), "more_body": False}

        await self.app(scope, replay_receive, send)
