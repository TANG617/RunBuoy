from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx

from runbuoy import __version__
from runbuoy.config import Config, CredentialStore
from runbuoy.networking.client import RemoteClient, flush_pending, repair_pending
from runbuoy.paths import AppPaths
from runbuoy.persistence.store import EventQueue


class RecordingClient:
    def __init__(self, fail_upload: bool = False, fail_metadata: bool = False) -> None:
        self.fail_upload = fail_upload
        self.fail_metadata = fail_metadata
        self.upserts: list[dict[str, Any]] = []
        self.batches: list[list[dict[str, Any]]] = []
        self.machine_updates: list[tuple[str, str]] = []

    def upsert_run(self, run: dict[str, Any]) -> None:
        self.upserts.append(run)

    def upload_events(self, _run_id: str, events: list[Any]) -> None:
        if self.fail_upload:
            raise OSError("offline")
        self.batches.append([event.model_dump(mode="json") for event in events])

    def update_machine(self, machine_id: str, display_name: str) -> None:
        if self.fail_metadata:
            raise OSError("offline")
        self.machine_updates.append((machine_id, display_name))


def test_run_upsert_sends_current_cli_version(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setenv("RUNBUOY_DISABLE_KEYRING", "1")
    paths = AppPaths(
        tmp_path / "config",
        tmp_path / "data",
        tmp_path / "state",
        tmp_path / "cache",
    )
    credentials = CredentialStore(paths)
    credentials.set("machine_credential", "machine-token")
    recorded: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        recorded.append(json.loads(request.content))
        return httpx.Response(200, json={})

    client = RemoteClient(
        Config(),
        credentials,
        transport=httpx.MockTransport(handler),
    )
    try:
        client.upsert_run(
            {
                "run_id": "019fac7f-e12a-7000-8000-000000000001",
                "machine_id": "machine-local",
                "title": "Safe title",
                "source": "cli",
            }
        )
    finally:
        client.close()
    assert recorded == [
        {
            "machine_id": "machine-local",
            "title": "Safe title",
            "source": "cli",
            "execution_status": "CREATED",
            "cli_version": __version__,
        }
    ]


def test_machine_update_uses_dedicated_endpoint(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setenv("RUNBUOY_DISABLE_KEYRING", "1")
    paths = AppPaths(
        tmp_path / "config",
        tmp_path / "data",
        tmp_path / "state",
        tmp_path / "cache",
    )
    credentials = CredentialStore(paths)
    credentials.set("machine_credential", "machine-token")
    recorded: list[tuple[str, str, dict[str, Any]]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        recorded.append((request.method, request.url.path, json.loads(request.content)))
        return httpx.Response(200, json={})

    client = RemoteClient(Config(), credentials, transport=httpx.MockTransport(handler))
    try:
        client.update_machine("machine-local", "Build Mac")
    finally:
        client.close()
    assert recorded == [("PATCH", "/v1/machines/machine-local", {"display_name": "Build Mac"})]


def test_pending_machine_name_is_last_write_wins_and_flushes_before_events(
    tmp_path: Path,
) -> None:
    queue = EventQueue(tmp_path / "db.sqlite3")
    queue.queue_machine_metadata("machine", "Old Name")
    queue.queue_machine_metadata("machine", "Build Mac")
    client = RecordingClient()

    assert flush_pending(queue, client, batch_size=20) == 0  # type: ignore[arg-type]
    assert client.machine_updates == [("machine", "Build Mac")]
    assert queue.pending_machine_metadata() is None


def test_fully_offline_terminal_run_replays_from_created(tmp_path: Path) -> None:
    queue = EventQueue(tmp_path / "db.sqlite3")
    queue.create_run(
        run_id="run",
        machine_id="machine",
        title="safe",
        manifest_path="local-manifest",
        log_path="local-log",
        result_path="local-result",
        socket_path="local-socket",
        tmux_session="local-tmux",
    )
    queue.append_event("run", "run.starting", {})
    queue.append_event("run", "run.started", {})
    queue.append_event("run", "run.succeeded", {"exit_code": 0})
    client = RecordingClient()
    assert flush_pending(queue, client, batch_size=20) == 4  # type: ignore[arg-type]
    assert [item["seq"] for item in client.batches[0]] == [1, 2, 3, 4]
    assert client.upserts[0]["status"] == "SUCCEEDED"
    assert queue.get_run("run")["remote_initialized"] == 1  # type: ignore[index]
    assert queue.pending_events() == []


def test_ambiguous_batch_retry_does_not_re_upsert_terminal_run(tmp_path: Path) -> None:
    queue = EventQueue(tmp_path / "db.sqlite3")
    queue.create_run(
        run_id="run",
        machine_id="machine",
        title="safe",
        manifest_path="m",
        log_path="l",
        result_path="r",
        socket_path="s",
        tmux_session="t",
    )
    offline = RecordingClient(fail_upload=True)
    assert flush_pending(queue, offline, batch_size=20) == 0  # type: ignore[arg-type]
    assert len(offline.upserts) == 1
    with queue.connect() as connection:
        connection.execute("UPDATE events SET next_attempt_at = 0")
    recovered = RecordingClient()
    assert flush_pending(queue, recovered, batch_size=20) == 1  # type: ignore[arg-type]
    assert recovered.upserts == []


def test_repair_forces_scheduled_events_and_drains_multiple_batches(tmp_path: Path) -> None:
    queue = EventQueue(tmp_path / "db.sqlite3")
    queue.create_run(
        run_id="run",
        machine_id="machine",
        title="safe",
        manifest_path="m",
        log_path="l",
        result_path="r",
        socket_path="s",
        tmux_session="t",
    )
    for sequence in range(4):
        queue.append_event("run", "run.message", {"message": f"safe-{sequence}"})
    with queue.connect() as connection:
        connection.execute(
            "UPDATE events SET attempt_count = 3, next_attempt_at = ?",
            (9_999_999_999,),
        )

    client = RecordingClient()
    result = repair_pending(queue, client, batch_size=2)  # type: ignore[arg-type]

    assert result.pending_events_before == 5
    assert result.delivered_events == 5
    assert result.pending_events_after == 0
    assert result.rounds == 3
    assert result.completed is True


def test_repair_failure_preserves_pending_events(tmp_path: Path) -> None:
    queue = EventQueue(tmp_path / "db.sqlite3")
    queue.create_run(
        run_id="run",
        machine_id="machine",
        title="safe",
        manifest_path="m",
        log_path="l",
        result_path="r",
        socket_path="s",
        tmux_session="t",
    )

    result = repair_pending(
        queue,
        RecordingClient(fail_upload=True),  # type: ignore[arg-type]
        batch_size=20,
    )

    assert result.delivered_events == 0
    assert result.pending_events_after == 1
    assert result.rounds == 1
    assert result.completed is False
