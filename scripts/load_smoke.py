from __future__ import annotations

import argparse
import concurrent.futures
import statistics
import time
import uuid
from datetime import UTC, datetime, timedelta
from urllib.parse import urlparse

import httpx

LOCAL_HOSTS = {"127.0.0.1", "::1", "localhost"}


def _expect(response: httpx.Response, expected: int) -> dict[str, object]:
    if response.status_code != expected:
        raise RuntimeError(f"request failed with HTTP {response.status_code}")
    if not response.content:
        return {}
    value = response.json()
    if not isinstance(value, dict):
        raise RuntimeError("request returned an unexpected response shape")
    return value


def _event(
    run_id: str,
    machine_id: str,
    sequence: int,
    event_type: str,
    occurred_at: datetime,
    payload: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "event_id": str(uuid.uuid4()),
        "run_id": run_id,
        "machine_id": machine_id,
        "seq": sequence,
        "type": event_type,
        "occurred_at": occurred_at.isoformat(),
        "payload": payload or {},
    }


def exercise_run(base_url: str, timeout: float, index: int) -> float:
    started = time.perf_counter()
    suffix = uuid.uuid4().hex
    with httpx.Client(base_url=base_url, timeout=timeout) as client:
        device = _expect(
            client.post(
                "/v1/devices/bootstrap",
                json={
                    "installation_id": f"load-smoke-{suffix}",
                    "app_version": "load-smoke",
                    "os_version": "18.0",
                },
            ),
            201,
        )
        pairing = _expect(
            client.post(
                "/v1/pairing-sessions",
                json={
                    "machine_id": f"load-machine-{suffix}",
                    "display_name": f"Load Smoke {index}",
                    "platform": "load-smoke",
                },
            ),
            201,
        )
        device_headers = {"Authorization": f"Bearer {device['credential']}"}
        _expect(
            client.post(
                f"/v1/pairing-sessions/{pairing['pairing_session_id']}/claim",
                headers=device_headers,
                json={"challenge": pairing["challenge"]},
            ),
            200,
        )
        machine = _expect(
            client.post(
                f"/v1/pairing-sessions/{pairing['pairing_session_id']}/exchange",
                json={"exchange_secret": pairing["exchange_secret"]},
            ),
            200,
        )
        machine_headers = {"Authorization": f"Bearer {machine['credential']}"}
        run_id = str(uuid.uuid4())
        _expect(
            client.put(
                f"/v1/runs/{run_id}",
                headers=machine_headers,
                json={
                    "machine_id": machine["machine_id"],
                    "title": "Synthetic load smoke",
                    "source": "load-smoke",
                    "live_activity_policy": "disabled",
                    "notification_policy": "none",
                },
            ),
            200,
        )
        now = datetime.now(UTC)
        events = [
            _event(run_id, str(machine["machine_id"]), 1, "run.created", now),
            _event(run_id, str(machine["machine_id"]), 2, "run.started", now),
            _event(
                run_id,
                str(machine["machine_id"]),
                3,
                "run.heartbeat",
                now + timedelta(milliseconds=10),
            ),
            _event(
                run_id,
                str(machine["machine_id"]),
                4,
                "run.progress",
                now + timedelta(milliseconds=20),
                {
                    "progress": {
                        "kind": "determinate",
                        "current": 1,
                        "total": 2,
                        "fraction": 0.5,
                        "source": "explicit",
                    }
                },
            ),
            _event(
                run_id,
                str(machine["machine_id"]),
                5,
                "run.succeeded",
                now + timedelta(milliseconds=30),
                {"exit_code": 0},
            ),
        ]
        result = _expect(
            client.post(
                f"/v1/runs/{run_id}/events:batch",
                headers=machine_headers,
                json={"events": events},
            ),
            200,
        )
        snapshot = result.get("snapshot")
        if not isinstance(snapshot, dict) or snapshot.get("execution_status") != "SUCCEEDED":
            raise RuntimeError("terminal projection was not returned")
    return time.perf_counter() - started


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    position = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * fraction)))
    return ordered[position]


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a bounded RunBuoy API lifecycle load smoke")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--concurrency", type=int, default=2)
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--confirm-remote", default="")
    args = parser.parse_args()
    parsed = urlparse(args.base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        parser.error("--base-url must be an HTTP(S) URL")
    if parsed.hostname not in LOCAL_HOSTS and args.confirm_remote != "RUNBUOY LOAD":
        parser.error("remote load requires --confirm-remote 'RUNBUOY LOAD'")
    if not 1 <= args.runs <= 1000:
        parser.error("--runs must be between 1 and 1000")
    if not 1 <= args.concurrency <= 50:
        parser.error("--concurrency must be between 1 and 50")

    latencies: list[float] = []
    wall_started = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as executor:
        futures = [
            executor.submit(exercise_run, args.base_url.rstrip("/"), args.timeout, index)
            for index in range(args.runs)
        ]
        for future in concurrent.futures.as_completed(futures):
            latencies.append(future.result())
    wall_seconds = time.perf_counter() - wall_started
    print(
        "RunBuoy load smoke: PASS "
        f"runs={len(latencies)} concurrency={args.concurrency} "
        f"wall={wall_seconds:.3f}s median={statistics.median(latencies):.3f}s "
        f"p95={percentile(latencies, 0.95):.3f}s"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
