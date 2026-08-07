from __future__ import annotations

import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier

import pytest
from sqlalchemy import Engine, create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.abuse import _increment_bucket, acquire_quota_lock
from app.config import Settings
from app.database import Base
from app.models import Machine, RateLimitBucket, Run, Workspace, utcnow


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
