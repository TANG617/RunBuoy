from __future__ import annotations

from collections.abc import Generator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.database import Base, get_session
from app.main import create_app


@dataclass(slots=True)
class Harness:
    client: TestClient
    session_factory: sessionmaker[Session]
    settings: Settings

    def bootstrap(self, installation_id: str = "ios-test") -> dict[str, str]:
        response = self.client.post(
            "/v1/devices/bootstrap",
            json={
                "installation_id": installation_id,
                "app_version": "1.0",
                "os_version": "18.0",
            },
        )
        assert response.status_code == 201, response.text
        return response.json()

    def pair(self, device: dict[str, str] | None = None) -> tuple[dict[str, str], dict[str, Any]]:
        device = device or self.bootstrap()
        created = self.client.post(
            "/v1/pairing-sessions",
            json={
                "display_name": "Test Mac",
                "hostname": "redacted-host",
                "platform": "darwin",
                "architecture": "arm64",
                "cli_version": "0.1",
            },
        )
        assert created.status_code == 201, created.text
        pairing = created.json()
        claimed = self.client.post(
            f"/v1/pairing-sessions/{pairing['pairing_session_id']}/claim",
            headers={"Authorization": f"Bearer {device['credential']}"},
            json={"challenge": pairing["challenge"]},
        )
        assert claimed.status_code == 200, claimed.text
        exchanged = self.client.post(
            f"/v1/pairing-sessions/{pairing['pairing_session_id']}/exchange",
            json={"exchange_secret": pairing["exchange_secret"]},
        )
        assert exchanged.status_code == 200, exchanged.text
        return device, {**pairing, **exchanged.json()}

    def register_run(self, machine: dict[str, Any], run_id: str) -> None:
        response = self.client.put(
            f"/v1/runs/{run_id}",
            headers={"Authorization": f"Bearer {machine['credential']}"},
            json={
                "machine_id": machine["machine_id"],
                "title": "Gurobi Experiment",
                "source": "cli",
                "execution_status": "SUCCEEDED",
                "progress": {"kind": "determinate", "fraction": 1.0},
            },
        )
        assert response.status_code == 200, response.text
        assert response.json()["execution_status"] == "CREATED"


@pytest.fixture
def harness(tmp_path: Path) -> Generator[Harness, None, None]:
    database_path = tmp_path / "test.db"
    settings = Settings(database_url=f"sqlite:///{database_path}")
    engine: Engine = create_engine(
        settings.database_url,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False, class_=Session)
    app = create_app(settings)

    def override_session() -> Generator[Session, None, None]:
        with factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    with TestClient(app) as client:
        yield Harness(client, factory, settings)
    Base.metadata.drop_all(engine)
    engine.dispose()
