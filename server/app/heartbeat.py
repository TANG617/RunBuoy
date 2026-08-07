from __future__ import annotations

import os
import socket
from collections.abc import Mapping

from sqlalchemy.orm import Session

from .models import ServiceHeartbeat, utcnow

WORKER_SERVICE = "outbox-worker"
_CLEANUP_COUNTER_KEYS = {
    "notifications",
    "events",
    "safe_log_tails",
    "pending_live_activities",
}


def worker_instance_id() -> str:
    configured = os.getenv("RUNBUOY_WORKER_INSTANCE_ID")
    if configured:
        return configured[:128]
    return socket.gethostname()[:128]


def record_heartbeat(
    session: Session,
    *,
    instance_id: str,
    status: str = "healthy",
    error_code: str | None = None,
    cleanup_counts: Mapping[str, int] | None = None,
) -> ServiceHeartbeat:
    if status not in {"healthy", "failed"}:
        raise ValueError("heartbeat status must be healthy or failed")
    now = utcnow()
    heartbeat = session.get(ServiceHeartbeat, (WORKER_SERVICE, instance_id))
    if heartbeat is None:
        heartbeat = ServiceHeartbeat(
            service_name=WORKER_SERVICE,
            instance_id=instance_id,
            status=status,
            started_at=now,
            last_seen_at=now,
            error_code=error_code,
            counters_json={},
        )
        session.add(heartbeat)
    else:
        heartbeat.status = status
        heartbeat.last_seen_at = now
        heartbeat.error_code = error_code
    if cleanup_counts:
        counters = dict(heartbeat.counters_json or {})
        for key, value in cleanup_counts.items():
            if key in _CLEANUP_COUNTER_KEYS:
                counters[key] = int(counters.get(key, 0)) + max(0, int(value))
        heartbeat.counters_json = counters
    session.commit()
    return heartbeat
