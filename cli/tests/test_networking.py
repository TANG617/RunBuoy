from __future__ import annotations

from pathlib import Path
from typing import Any

from runbuoy.networking.client import flush_pending
from runbuoy.persistence.store import EventQueue


class RecordingClient:
    def __init__(self, fail_upload: bool = False) -> None:
        self.fail_upload = fail_upload
        self.upserts: list[dict[str, Any]] = []
        self.batches: list[list[dict[str, Any]]] = []

    def upsert_run(self, run: dict[str, Any]) -> None:
        self.upserts.append(run)

    def upload_events(self, _run_id: str, events: list[Any]) -> None:
        if self.fail_upload:
            raise OSError("offline")
        self.batches.append([event.model_dump(mode="json") for event in events])


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
