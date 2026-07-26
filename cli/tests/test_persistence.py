from __future__ import annotations

import json
from pathlib import Path

import pytest

from runbuoy.persistence.store import EventQueue


def create_run(queue: EventQueue, tmp_path: Path, run_id: str = "run") -> None:
    queue.create_run(
        run_id=run_id,
        machine_id="machine_local",
        title="python · test.py",
        manifest_path=str(tmp_path / "manifest"),
        log_path=str(tmp_path / "log"),
        result_path=str(tmp_path / "result"),
        socket_path=str(tmp_path / "socket"),
        tmux_session="runbuoy-run",
    )


def test_event_seq_and_snapshot_are_one_transaction(tmp_path: Path) -> None:
    queue = EventQueue(tmp_path / "state.sqlite3")
    create_run(queue, tmp_path)
    started = queue.append_event("run", "run.starting", {})
    running = queue.append_event("run", "run.started", {})
    progress = queue.append_event(
        "run",
        "run.progress",
        {
            "progress": {
                "kind": "determinate",
                "current": 2,
                "total": 4,
                "fraction": 0.5,
                "source": "lines",
            }
        },
    )
    assert [started.seq, running.seq, progress.seq] == [2, 3, 4]
    assert queue.get_run("run")["progress"]["fraction"] == 0.5  # type: ignore[index]


def test_terminal_state_is_immutable(tmp_path: Path) -> None:
    queue = EventQueue(tmp_path / "state.sqlite3")
    create_run(queue, tmp_path)
    queue.append_event("run", "run.succeeded", {"exit_code": 0})
    with pytest.raises(ValueError, match="terminal"):
        queue.append_event("run", "run.message", {"message": "late"})


def test_outbox_retry_preserves_event_and_attempt_count(tmp_path: Path) -> None:
    queue = EventQueue(tmp_path / "state.sqlite3")
    create_run(queue, tmp_path)
    event = queue.pending_events()[0]
    queue.mark_failed([event.event_id], "offline token=secret", 0)
    retried = queue.pending_events()[0]
    assert retried.event_id == event.event_id
    row = queue.event_rows("run")[0]
    assert row["attempt_count"] == 1
    queue.mark_delivered([event.event_id])
    assert queue.pending_events() == []


def test_default_remote_event_has_no_execution_details(tmp_path: Path) -> None:
    queue = EventQueue(tmp_path / "state.sqlite3")
    create_run(queue, tmp_path)
    payload = json.loads(queue.event_rows("run")[0]["event_json"])
    serialized = json.dumps(payload)
    for forbidden in ("argv", "cwd", "env", "stdout", "stderr"):
        assert forbidden not in serialized
