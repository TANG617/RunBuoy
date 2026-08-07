from __future__ import annotations

import os
import uuid
from collections.abc import Generator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.abuse import _increment_bucket, acquire_quota_lock
from app.config import Settings
from app.database import Base, get_session
from app.main import create_app
from app.models import (
    Device,
    Machine,
    MachineCredential,
    MachineDeviceSubscription,
    PairingSession,
    RateLimitBucket,
    Run,
    RunEvent,
    Workspace,
    utcnow,
)


@pytest.fixture
def postgres_factory() -> sessionmaker[Session]:
    database_url = os.getenv("RUNBUOY_TEST_POSTGRES_URL") or os.getenv("DATABASE_URL")
    if not database_url:
        pytest.skip(
            "RUNBUOY_TEST_POSTGRES_URL or DATABASE_URL is required for PostgreSQL concurrency tests"
        )
    engine: Engine = create_engine(database_url, pool_size=20, max_overflow=20)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False, class_=Session)
    try:
        yield factory
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture
def postgres_client(
    postgres_factory: sessionmaker[Session],
) -> Generator[tuple[TestClient, sessionmaker[Session]], None, None]:
    settings = Settings(database_url="postgresql+psycopg://concurrency-test")
    app = create_app(settings)

    def override_session() -> Generator[Session, None, None]:
        with postgres_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    with TestClient(app) as client:
        yield client, postgres_factory


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _bootstrap(client: TestClient, installation_id: str) -> dict[str, str]:
    response = client.post(
        "/v1/devices/bootstrap",
        json={"installation_id": installation_id},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _pair(client: TestClient) -> tuple[dict[str, str], dict[str, Any]]:
    device = _bootstrap(client, f"postgres-{uuid.uuid4()}")
    created = client.post(
        "/v1/pairing-sessions",
        json={"machine_id": f"machine-{uuid.uuid4()}", "display_name": "PG Mac"},
    ).json()
    claimed = client.post(
        f"/v1/pairing-sessions/{created['pairing_session_id']}/claim",
        headers=_auth(device["credential"]),
        json={"challenge": created["challenge"]},
    )
    assert claimed.status_code == 200, claimed.text
    exchanged = client.post(
        f"/v1/pairing-sessions/{created['pairing_session_id']}/exchange",
        json={"exchange_secret": created["exchange_secret"]},
    )
    assert exchanged.status_code == 200, exchanged.text
    return device, {**created, **exchanged.json()}


def test_postgres_rate_limit_upsert_is_atomic(
    postgres_factory: sessionmaker[Session],
) -> None:
    workers = 32
    barrier = Barrier(workers)
    now = utcnow()

    def consume() -> int:
        with postgres_factory() as session:
            barrier.wait()
            count = _increment_bucket(
                session,
                bucket_name="concurrency",
                subject_key="a" * 64,
                window_start=int(now.timestamp()),
                expires_at=now + timedelta(minutes=2),
                now=now,
            )
            session.commit()
            return count

    with ThreadPoolExecutor(max_workers=workers) as executor:
        counts = list(executor.map(lambda _index: consume(), range(workers)))

    assert sorted(counts) == list(range(1, workers + 1))
    with postgres_factory() as session:
        bucket = session.scalar(select(RateLimitBucket))
        assert bucket is not None
        assert bucket.request_count == workers


def test_postgres_quota_lock_prevents_concurrent_active_run_overflow(
    postgres_factory: sessionmaker[Session],
) -> None:
    settings = Settings(max_active_runs_per_machine=5)
    with postgres_factory() as session:
        session.add(Workspace(id="workspace-concurrency"))
        session.flush()
        session.add(
            Machine(
                id="machine-concurrency",
                workspace_id="workspace-concurrency",
                display_name="Concurrent machine",
            )
        )
        session.commit()

    workers = 20
    barrier = Barrier(workers)

    def create_if_available() -> bool:
        with postgres_factory() as session:
            barrier.wait()
            acquire_quota_lock(
                session,
                settings,
                namespace="machine_active_runs",
                subject="machine-concurrency",
            )
            active = session.scalar(
                select(func.count())
                .select_from(Run)
                .where(
                    Run.machine_id == "machine-concurrency",
                    ~Run.execution_status.in_(("SUCCEEDED", "FAILED", "CANCELLED", "LOST")),
                )
            )
            if int(active or 0) >= settings.max_active_runs_per_machine:
                session.commit()
                return False
            session.add(
                Run(
                    id=str(uuid.uuid4()),
                    workspace_id="workspace-concurrency",
                    machine_id="machine-concurrency",
                    title="Concurrent run",
                )
            )
            session.commit()
            return True

    with ThreadPoolExecutor(max_workers=workers) as executor:
        created = list(executor.map(lambda _index: create_if_available(), range(workers)))

    assert sum(created) == settings.max_active_runs_per_machine
    with postgres_factory() as session:
        assert session.scalar(select(func.count()).select_from(Run)) == 5


def test_postgres_pairing_claim_is_concurrently_single_use(
    postgres_client: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, factory = postgres_client
    devices = [
        _bootstrap(client, "claim-workspace-one"),
        _bootstrap(client, "claim-workspace-two"),
    ]
    pairing = client.post(
        "/v1/pairing-sessions",
        json={"display_name": "One claim only"},
    ).json()
    barrier = Barrier(2)

    def claim(device: dict[str, str]) -> int:
        barrier.wait()
        return client.post(
            f"/v1/pairing-sessions/{pairing['pairing_session_id']}/claim",
            headers=_auth(device["credential"]),
            json={"challenge": pairing["challenge"]},
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        statuses = list(executor.map(claim, devices))

    assert sorted(statuses) == [200, 409]
    with factory() as session:
        stored = session.get(PairingSession, pairing["pairing_session_id"])
        assert stored is not None
        assert stored.workspace_id in {device["workspace_id"] for device in devices}
        assert session.scalar(select(func.count()).select_from(Machine)) == 1
        assert session.scalar(select(func.count()).select_from(MachineDeviceSubscription)) == 1


def test_postgres_anonymous_bootstrap_is_concurrently_create_only(
    postgres_client: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, factory = postgres_client
    barrier = Barrier(2)

    def bootstrap(_index: int) -> int:
        barrier.wait()
        return client.post(
            "/v1/devices/bootstrap",
            json={"installation_id": "same-concurrent-installation"},
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        statuses = list(executor.map(bootstrap, range(2)))

    assert sorted(statuses) == [201, 409]
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(Device)) == 1
        assert session.scalar(select(func.count()).select_from(Workspace)) == 1


def test_postgres_pairing_exchange_issues_only_one_credential(
    postgres_client: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, factory = postgres_client
    device = _bootstrap(client, "exchange-workspace")
    pairing = client.post(
        "/v1/pairing-sessions",
        json={"display_name": "One exchange only"},
    ).json()
    claimed = client.post(
        f"/v1/pairing-sessions/{pairing['pairing_session_id']}/claim",
        headers=_auth(device["credential"]),
        json={"challenge": pairing["challenge"]},
    )
    assert claimed.status_code == 200
    barrier = Barrier(2)

    def exchange(_index: int) -> int:
        barrier.wait()
        return client.post(
            f"/v1/pairing-sessions/{pairing['pairing_session_id']}/exchange",
            json={"exchange_secret": pairing["exchange_secret"]},
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        statuses = list(executor.map(exchange, range(2)))

    assert sorted(statuses) == [200, 409]
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(MachineCredential)) == 1


def test_postgres_concurrent_event_batches_never_regress_projection(
    postgres_client: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, factory = postgres_client
    _device, machine = _pair(client)
    run_id = str(uuid.uuid4())
    registered = client.put(
        f"/v1/runs/{run_id}",
        headers=_auth(machine["credential"]),
        json={"machine_id": machine["machine_id"], "title": "Concurrent events"},
    )
    assert registered.status_code == 200
    barrier = Barrier(2)

    def post(seq: int) -> int:
        barrier.wait()
        return client.post(
            f"/v1/runs/{run_id}/events:batch",
            headers=_auth(machine["credential"]),
            json={
                "events": [
                    {
                        "schema_version": 1,
                        "event_id": str(uuid.uuid4()),
                        "run_id": run_id,
                        "machine_id": machine["machine_id"],
                        "seq": seq,
                        "type": "run.progress",
                        "occurred_at": datetime.now(UTC).isoformat(),
                        "payload": {"phase": f"phase-{seq}"},
                    }
                ]
            },
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        statuses = list(executor.map(post, (1, 2)))

    assert all(value in {200, 409} for value in statuses)
    assert 200 in statuses
    with factory() as session:
        stored = session.get(Run, run_id)
        event_seqs = list(
            session.scalars(
                select(RunEvent.seq).where(RunEvent.run_id == run_id).order_by(RunEvent.seq)
            )
        )
        assert stored is not None
        assert stored.last_seq == max(event_seqs)
        assert stored.phase == f"phase-{stored.last_seq}"


def test_postgres_concurrent_webhook_events_receive_distinct_sequences(
    postgres_client: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, factory = postgres_client
    _device, machine = _pair(client)
    hook = client.post(
        "/v1/webhooks",
        headers=_auth(machine["credential"]),
        json={"name": "Concurrent hook"},
    ).json()
    external_id = "parallel-build"
    registered = client.put(
        f"/v1/hooks/{hook['hook_id']}/runs/{external_id}",
        headers=_auth(hook["secret"]),
        json={"machine_id": machine["machine_id"], "title": "Webhook run"},
    )
    assert registered.status_code == 200, registered.text
    run_id = registered.json()["id"]
    barrier = Barrier(2)

    def post(index: int) -> int:
        barrier.wait()
        return client.post(
            f"/v1/hooks/{hook['hook_id']}/runs/{external_id}/events",
            headers={**_auth(hook["secret"]), "Idempotency-Key": f"parallel-{index}"},
            json={"type": "run.progress", "phase": f"phase-{index}"},
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        statuses = list(executor.map(post, range(2)))

    assert statuses == [202, 202]
    with factory() as session:
        assert list(
            session.scalars(
                select(RunEvent.seq).where(RunEvent.run_id == run_id).order_by(RunEvent.seq)
            )
        ) == [1, 2]
        stored = session.get(Run, run_id)
        assert stored is not None and stored.last_seq == 2
