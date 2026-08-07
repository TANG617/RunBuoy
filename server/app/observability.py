from __future__ import annotations

import hashlib
import json
import logging
import math
import re
import threading
import time
import uuid
from collections import defaultdict
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi import Depends, FastAPI, Request, Response
from fastapi.responses import JSONResponse, PlainTextResponse
from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from .config import Settings
from .database import get_session
from .heartbeat import WORKER_SERVICE
from .models import LiveActivityBinding, PushAttempt, PushOutbox, ServiceHeartbeat, utcnow

REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
HTTP_DURATION_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0)
OUTBOX_STATES = ("pending", "sent", "failed", "expired", "suppressed", "cancelled")
APNS_STATUS_CLASSES = ("2xx", "4xx", "5xx", "other")
APNS_REASON_CLASSES = (
    "none",
    "invalid_token",
    "throttled",
    "authentication",
    "bad_request",
    "transient",
    "other",
)
SYNC_OUTCOMES = ("hit", "not_modified", "fallback")

request_logger = logging.getLogger("runbuoy.request")


def configure_request_logging() -> None:
    if request_logger.handlers:
        return
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    request_logger.addHandler(handler)
    request_logger.setLevel(logging.INFO)
    request_logger.propagate = False


def _request_id(value: str | None) -> str:
    if value is not None and REQUEST_ID_PATTERN.fullmatch(value):
        return "req_" + hashlib.sha256(value.encode()).hexdigest()[:32]
    return uuid.uuid4().hex


def _route_template(request: Request) -> str:
    route = request.scope.get("route")
    path = getattr(route, "path", None)
    return str(path) if path else "unmatched"


def request_log_event(
    *,
    request_id: str,
    method: str,
    route: str,
    status_code: int,
    latency_seconds: float,
    error_class: str | None = None,
) -> dict[str, object]:
    event: dict[str, object] = {
        "event": "http_request",
        "request_id": request_id,
        "method": method,
        "route": route,
        "status": status_code,
        "latency_ms": round(latency_seconds * 1000, 3),
    }
    if error_class is not None:
        event["error_class"] = error_class
    return event


SENSITIVE_KEY_PARTS = {
    "authorization",
    "body",
    "credential",
    "payload",
    "private_key",
    "qr",
    "query",
    "safe_log_tail",
    "safe_message",
    "secret",
    "token",
}


def redact_sensitive(value: object) -> object:
    """Redact defensive structured-log values; request logs use an allowlist."""
    if isinstance(value, Mapping):
        redacted: dict[str, object] = {}
        for key, item in value.items():
            normalized = str(key).lower()
            if any(part in normalized for part in SENSITIVE_KEY_PARTS):
                redacted[str(key)] = "[REDACTED]"
            else:
                redacted[str(key)] = redact_sensitive(item)
        return redacted
    if isinstance(value, list | tuple):
        return [redact_sensitive(item) for item in value]
    return value


def _label_value(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


def _labels(values: Mapping[str, str]) -> str:
    if not values:
        return ""
    rendered = ",".join(f'{key}="{_label_value(value)}"' for key, value in sorted(values.items()))
    return "{" + rendered + "}"


class MetricsRegistry:
    """Small in-process registry with fixed, low-cardinality label domains."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._http_requests: dict[tuple[str, str, str], int] = defaultdict(int)
        self._http_duration_count: dict[tuple[str, str], int] = defaultdict(int)
        self._http_duration_sum: dict[tuple[str, str], float] = defaultdict(float)
        self._http_duration_buckets: dict[tuple[str, str, float], int] = defaultdict(int)
        self._rate_limits: dict[str, int] = defaultdict(int)
        self._sync: dict[str, int] = defaultdict(int)

    def reset_for_test(self) -> None:
        with self._lock:
            self._http_requests.clear()
            self._http_duration_count.clear()
            self._http_duration_sum.clear()
            self._http_duration_buckets.clear()
            self._rate_limits.clear()
            self._sync.clear()

    def record_http(self, method: str, route: str, status_code: int, latency: float) -> None:
        normalized_method = (
            method if method in {"GET", "POST", "PUT", "PATCH", "DELETE"} else "OTHER"
        )
        status_class = f"{status_code // 100}xx" if 100 <= status_code <= 599 else "other"
        key = (normalized_method, route, status_class)
        duration_key = (normalized_method, route)
        with self._lock:
            self._http_requests[key] += 1
            self._http_duration_count[duration_key] += 1
            self._http_duration_sum[duration_key] += max(0.0, latency)
            for bucket in HTTP_DURATION_BUCKETS:
                if latency <= bucket:
                    self._http_duration_buckets[(*duration_key, bucket)] += 1

    def record_rate_limit(self, route: str) -> None:
        with self._lock:
            self._rate_limits[route] += 1

    def record_sync(self, outcome: str) -> None:
        if outcome not in SYNC_OUTCOMES:
            raise ValueError("unsupported sync metrics outcome")
        with self._lock:
            self._sync[outcome] += 1

    def _render_process_metrics(self) -> list[str]:
        with self._lock:
            requests = dict(self._http_requests)
            duration_count = dict(self._http_duration_count)
            duration_sum = dict(self._http_duration_sum)
            duration_buckets = dict(self._http_duration_buckets)
            rate_limits = dict(self._rate_limits)
            sync = dict(self._sync)
        lines = [
            "# HELP runbuoy_http_requests_total HTTP responses by route template and status class.",
            "# TYPE runbuoy_http_requests_total counter",
        ]
        for (method, route, status_class), value in sorted(requests.items()):
            labels = _labels({"method": method, "route": route, "status_class": status_class})
            lines.append(f"runbuoy_http_requests_total{labels} {value}")
        lines.extend(
            [
                "# HELP runbuoy_http_request_duration_seconds HTTP request latency.",
                "# TYPE runbuoy_http_request_duration_seconds histogram",
            ]
        )
        for (method, route), count in sorted(duration_count.items()):
            base = {"method": method, "route": route}
            for bucket in HTTP_DURATION_BUCKETS:
                labels = _labels({**base, "le": f"{bucket:g}"})
                value = duration_buckets.get((method, route, bucket), 0)
                lines.append(f"runbuoy_http_request_duration_seconds_bucket{labels} {value}")
            lines.append(
                "runbuoy_http_request_duration_seconds_bucket"
                f"{_labels({**base, 'le': '+Inf'})} {count}"
            )
            lines.append(
                f"runbuoy_http_request_duration_seconds_sum{_labels(base)} "
                f"{duration_sum[(method, route)]:.9f}"
            )
            lines.append(f"runbuoy_http_request_duration_seconds_count{_labels(base)} {count}")
        lines.extend(
            [
                "# HELP runbuoy_rate_limit_rejections_total Requests rejected by rate limiting.",
                "# TYPE runbuoy_rate_limit_rejections_total counter",
            ]
        )
        for route, value in sorted(rate_limits.items()):
            lines.append(f"runbuoy_rate_limit_rejections_total{_labels({'route': route})} {value}")
        lines.extend(
            [
                "# HELP runbuoy_sync_requests_total Read/sync cache outcomes.",
                "# TYPE runbuoy_sync_requests_total counter",
            ]
        )
        for outcome in SYNC_OUTCOMES:
            lines.append(
                f"runbuoy_sync_requests_total{_labels({'outcome': outcome})} {sync.get(outcome, 0)}"
            )
        return lines

    def render(self, session: Session) -> str:
        lines = self._render_process_metrics()
        lines.extend(_render_database_metrics(session))
        return "\n".join(lines) + "\n"


metrics = MetricsRegistry()


def classify_apns_reason(status_code: int, reason: str | None) -> str:
    if status_code == 410 or reason in {
        "BadDeviceToken",
        "DeviceTokenNotForTopic",
        "ExpiredToken",
        "Unregistered",
    }:
        return "invalid_token"
    if status_code == 429:
        return "throttled"
    if status_code in {401, 403}:
        return "authentication"
    if status_code >= 500:
        return "transient"
    if 400 <= status_code < 500:
        return "bad_request"
    if reason:
        return "other"
    return "none"


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _render_database_metrics(session: Session) -> list[str]:
    now = utcnow()
    status_rows: dict[str, int] = {
        status: int(count)
        for status, count in session.execute(
            select(PushOutbox.status, func.count()).group_by(PushOutbox.status)
        )
    }
    oldest = session.scalar(
        select(func.min(PushOutbox.created_at)).where(PushOutbox.status == "pending")
    )
    oldest_age = max(0.0, (now - _aware(oldest)).total_seconds()) if oldest else 0.0
    active_bindings = int(
        session.scalar(
            select(func.count())
            .select_from(LiveActivityBinding)
            .where(
                LiveActivityBinding.state.in_(("active", "stale")),
                LiveActivityBinding.invalidated_at.is_(None),
            )
        )
        or 0
    )
    apns_counts: dict[tuple[str, str], int] = defaultdict(int)
    invalid_tokens = 0
    # Aggregate in SQL so a metrics scrape is bounded by the APNs outcome
    # vocabulary rather than materializing every retained attempt row.
    attempts = session.execute(
        select(PushAttempt.status_code, PushAttempt.reason, func.count()).group_by(
            PushAttempt.status_code, PushAttempt.reason
        )
    )
    for status_code, reason, count in attempts:
        status_class = f"{status_code // 100}xx" if 200 <= status_code <= 599 else "other"
        reason_class = classify_apns_reason(status_code, reason)
        apns_counts[(status_class, reason_class)] += int(count)
        if reason_class == "invalid_token":
            invalid_tokens += int(count)
    queue_sum, queue_count, provider_sum, provider_count = session.execute(
        select(
            func.coalesce(func.sum(PushAttempt.queue_latency_ms), 0),
            func.count(PushAttempt.queue_latency_ms),
            func.coalesce(func.sum(PushAttempt.provider_latency_ms), 0),
            func.count(PushAttempt.provider_latency_ms),
        )
    ).one()
    heartbeats = list(
        session.scalars(
            select(ServiceHeartbeat).where(ServiceHeartbeat.service_name == WORKER_SERVICE)
        )
    )
    healthy_ages = [
        max(0.0, (now - _aware(row.last_seen_at)).total_seconds())
        for row in heartbeats
        if row.status == "healthy"
    ]
    heartbeat_age = min(healthy_ages) if healthy_ages else math.inf
    heartbeat_age_text = f"{heartbeat_age:.6f}" if math.isfinite(heartbeat_age) else "+Inf"
    cleanup_totals: dict[str, int] = defaultdict(int)
    for heartbeat in heartbeats:
        for key, value in (heartbeat.counters_json or {}).items():
            if key in {
                "notifications",
                "events",
                "safe_log_tails",
                "pending_live_activities",
            }:
                cleanup_totals[key] += int(value)
    healthy_workers = sum(row.status == "healthy" for row in heartbeats)
    failed_workers = sum(row.status == "failed" for row in heartbeats)

    lines = [
        "# HELP runbuoy_outbox_items Current push outbox items by state.",
        "# TYPE runbuoy_outbox_items gauge",
    ]
    for state in OUTBOX_STATES:
        lines.append(
            f"runbuoy_outbox_items{_labels({'state': state})} {int(status_rows.get(state, 0))}"
        )
    lines.extend(
        [
            "# HELP runbuoy_outbox_oldest_pending_age_seconds Age of the oldest pending push.",
            "# TYPE runbuoy_outbox_oldest_pending_age_seconds gauge",
            f"runbuoy_outbox_oldest_pending_age_seconds {oldest_age:.6f}",
            "# HELP runbuoy_apns_responses_total Durable APNs outcomes by bounded class.",
            "# TYPE runbuoy_apns_responses_total counter",
        ]
    )
    for status_class in APNS_STATUS_CLASSES:
        for reason_class in APNS_REASON_CLASSES:
            value = apns_counts.get((status_class, reason_class), 0)
            lines.append(
                "runbuoy_apns_responses_total"
                f"{_labels({'reason_class': reason_class, 'status_class': status_class})} {value}"
            )
    lines.extend(
        [
            "# HELP runbuoy_apns_queue_latency_seconds Durable APNs queue latency.",
            "# TYPE runbuoy_apns_queue_latency_seconds summary",
            f"runbuoy_apns_queue_latency_seconds_sum {float(queue_sum) / 1000:.6f}",
            f"runbuoy_apns_queue_latency_seconds_count {int(queue_count)}",
            "# HELP runbuoy_apns_provider_latency_seconds Durable APNs provider latency.",
            "# TYPE runbuoy_apns_provider_latency_seconds summary",
            f"runbuoy_apns_provider_latency_seconds_sum {float(provider_sum) / 1000:.6f}",
            f"runbuoy_apns_provider_latency_seconds_count {int(provider_count)}",
            "# HELP runbuoy_apns_invalid_tokens_total APNs responses that invalidate a token.",
            "# TYPE runbuoy_apns_invalid_tokens_total counter",
            f"runbuoy_apns_invalid_tokens_total {invalid_tokens}",
            "# HELP runbuoy_active_live_activity_bindings Current active or stale bindings.",
            "# TYPE runbuoy_active_live_activity_bindings gauge",
            f"runbuoy_active_live_activity_bindings {active_bindings}",
            "# HELP runbuoy_worker_heartbeat_age_seconds Age of the freshest healthy worker.",
            "# TYPE runbuoy_worker_heartbeat_age_seconds gauge",
            f"runbuoy_worker_heartbeat_age_seconds {heartbeat_age_text}",
            "# HELP runbuoy_worker_instances Worker instances by reported status.",
            "# TYPE runbuoy_worker_instances gauge",
            f'runbuoy_worker_instances{{status="healthy"}} {healthy_workers}',
            f'runbuoy_worker_instances{{status="failed"}} {failed_workers}',
            "# HELP runbuoy_cleanup_deleted_rows_total Rows cleaned by workers.",
            "# TYPE runbuoy_cleanup_deleted_rows_total counter",
        ]
    )
    for table in sorted(("notifications", "events", "safe_log_tails", "pending_live_activities")):
        lines.append(
            f"runbuoy_cleanup_deleted_rows_total{_labels({'table': table})} "
            f"{cleanup_totals.get(table, 0)}"
        )
    return lines


def expected_alembic_head() -> str:
    server_root = Path(__file__).resolve().parent.parent
    config = Config(str(server_root / "alembic.ini"))
    config.set_main_option("script_location", str(server_root / "migrations"))
    heads = ScriptDirectory.from_config(config).get_heads()
    if len(heads) != 1:
        raise RuntimeError("database migration graph must have exactly one head")
    return heads[0]


def readiness_report(session: Session, settings: Settings) -> tuple[bool, dict[str, object]]:
    checks: dict[str, dict[str, object]] = {}
    try:
        session.execute(text("SELECT 1"))
        checks["database"] = {"status": "ok"}
    except SQLAlchemyError as error:
        session.rollback()
        checks["database"] = {"status": "failed", "error": type(error).__name__}

    try:
        expected = expected_alembic_head()
        current = session.scalar(text("SELECT version_num FROM alembic_version"))
        migration_ok = current == expected
        checks["migration"] = {
            "status": "ok" if migration_ok else "failed",
            "current": current or "missing",
            "expected": expected,
        }
    except (SQLAlchemyError, RuntimeError) as error:
        session.rollback()
        checks["migration"] = {"status": "failed", "error": type(error).__name__}

    config_errors = settings.configuration_errors()
    checks["configuration"] = {
        "status": "ok" if not config_errors else "failed",
        "invalid": config_errors,
    }

    if not settings.worker_heartbeat_required:
        checks["worker"] = {"status": "disabled"}
    else:
        now = utcnow()
        try:
            workers = list(
                session.scalars(
                    select(ServiceHeartbeat).where(ServiceHeartbeat.service_name == WORKER_SERVICE)
                )
            )
            healthy_ages = [
                max(0.0, (now - _aware(worker.last_seen_at)).total_seconds())
                for worker in workers
                if worker.status == "healthy"
            ]
            age = min(healthy_ages) if healthy_ages else None
            fresh = age is not None and age <= settings.worker_heartbeat_max_age_seconds
            checks["worker"] = {
                "status": "ok" if fresh else "failed",
                "fresh_healthy_instances": sum(
                    worker.status == "healthy"
                    and (now - _aware(worker.last_seen_at)).total_seconds()
                    <= settings.worker_heartbeat_max_age_seconds
                    for worker in workers
                ),
                "failed_instances": sum(worker.status == "failed" for worker in workers),
                "freshest_age_seconds": round(age, 3) if age is not None else None,
                "max_age_seconds": settings.worker_heartbeat_max_age_seconds,
            }
        except SQLAlchemyError as error:
            session.rollback()
            checks["worker"] = {"status": "failed", "error": type(error).__name__}
    ready = all(check["status"] in {"ok", "disabled"} for check in checks.values())
    return ready, {
        "status": "ready" if ready else "not_ready",
        "region": settings.region,
        "checks": checks,
    }


def install_observability(application: FastAPI) -> None:
    configure_request_logging()

    @application.middleware("http")
    async def observe_request(request: Request, call_next: Any) -> Response:
        request_id = _request_id(request.headers.get("x-request-id"))
        started = time.perf_counter()
        status_code = 500
        error_class: str | None = None
        sync_outcome: str | None = None
        try:
            response = await call_next(request)
            status_code = response.status_code
            route = _route_template(request)
            if status_code == 429:
                metrics.record_rate_limit(route)
            if request.method == "GET" and route == "/v1/sync":
                hinted_outcome = response.headers.get("X-RunBuoy-Sync-Outcome")
                if hinted_outcome in SYNC_OUTCOMES:
                    sync_outcome = hinted_outcome
                elif status_code == 304:
                    sync_outcome = "not_modified"
                elif 200 <= status_code < 300:
                    sync_outcome = "hit"
                if sync_outcome is not None:
                    metrics.record_sync(sync_outcome)
            response.headers["X-Request-ID"] = request_id
            return response
        except Exception as error:
            error_class = type(error).__name__
            raise
        finally:
            latency = time.perf_counter() - started
            route = _route_template(request)
            metrics.record_http(request.method, route, status_code, latency)
            event = request_log_event(
                request_id=request_id,
                method=request.method,
                route=route,
                status_code=status_code,
                latency_seconds=latency,
                error_class=error_class,
            )
            request_logger.info(json.dumps(event, separators=(",", ":"), sort_keys=True))

    @application.get("/readyz", include_in_schema=False)
    def ready_endpoint(session: Session = Depends(get_session)) -> JSONResponse:
        is_ready, report = readiness_report(session, application.state.settings)
        return JSONResponse(report, status_code=200 if is_ready else 503)

    @application.get("/metrics", include_in_schema=False)
    def metrics_endpoint(session: Session = Depends(get_session)) -> PlainTextResponse:
        return PlainTextResponse(
            metrics.render(session),
            media_type="text/plain; version=0.0.4; charset=utf-8",
        )
