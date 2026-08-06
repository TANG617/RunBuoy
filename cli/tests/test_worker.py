from __future__ import annotations

import json
import os
import socket
import sys
import threading
import time
from pathlib import Path

from runbuoy.config import ephemeral_token
from runbuoy.models import ProgressMode, RunManifest
from runbuoy.paths import AppPaths
from runbuoy.persistence.store import EventQueue
from runbuoy.worker.runtime import run_worker


def prepare_manifest(
    tmp_path: Path,
    argv: list[str],
    *,
    mode: ProgressMode = ProgressMode.INDETERMINATE,
    pattern: str | None = None,
) -> tuple[Path, EventQueue]:
    paths = AppPaths(
        tmp_path / "config",
        tmp_path / "data",
        tmp_path / "state",
        tmp_path / "cache",
    )
    paths.ensure()
    os.environ["RUNBUOY_HOME"] = str(tmp_path)
    run_id = "0190f2a0-a003-7abc-8def-0123456789ab"
    directory = paths.run_dir(run_id)
    manifest_path = directory / "manifest.json"
    manifest = RunManifest(
        run_id=run_id,
        machine_id="machine-test",
        title="python · test",
        argv=argv,
        cwd=str(tmp_path),
        progress_mode=mode,
        pattern=pattern,
        socket_path=str(paths.event_socket(run_id)),
        socket_token=ephemeral_token(),
        handoff_path=str(directory / "handoff.json"),
        handoff_nonce=ephemeral_token(),
        handoff_timeout_seconds=2,
        log_path=str(directory / "run.log"),
        result_path=str(directory / "result.json"),
    )
    manifest.write_securely(manifest_path)
    queue = EventQueue(paths.database)
    queue.create_run(
        run_id=run_id,
        machine_id=manifest.machine_id,
        title=manifest.title,
        manifest_path=str(manifest_path),
        log_path=manifest.log_path,
        result_path=manifest.result_path,
        socket_path=manifest.socket_path,
        tmux_session=None,
    )
    return manifest_path, queue


def run_with_handoff(manifest_path: Path) -> int:
    manifest = RunManifest.model_validate_json(manifest_path.read_text())
    acknowledged = threading.Event()

    def acknowledge() -> None:
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            if Path(manifest.handoff_path).exists() and Path(manifest.socket_path).is_socket():
                with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                    client.connect(manifest.socket_path)
                    client.sendall(
                        json.dumps(
                            {
                                "token": manifest.socket_token,
                                "kind": "handoff_ack",
                                "nonce": manifest.handoff_nonce,
                            }
                        ).encode()
                        + b"\n"
                    )
                    response = json.loads(client.recv(4096))
                    assert response["ok"] is True
                    acknowledged.set()
                    return
            time.sleep(0.01)

    thread = threading.Thread(target=acknowledge)
    thread.start()
    result = run_worker(manifest_path)
    thread.join(2)
    assert acknowledged.is_set()
    return result


def test_worker_captures_real_exit_and_final_result(tmp_path: Path) -> None:
    manifest, queue = prepare_manifest(
        tmp_path,
        [sys.executable, "-c", "print('safe local output')"],
    )
    try:
        assert run_with_handoff(manifest) == 0
    finally:
        os.environ.pop("RUNBUOY_HOME")
    run = queue.get_run("0190f2a0-a003-7abc-8def-0123456789ab")
    assert run is not None
    assert run["status"] == "SUCCEEDED"
    assert run["exit_code"] == 0
    result = json.loads(Path(run["result_path"]).read_text())
    assert result["status"] == "SUCCEEDED"
    assert Path(run["result_path"]).stat().st_mode & 0o077 == 0


def test_worker_regex_progress_across_target_writes(tmp_path: Path) -> None:
    script = (
        "import os,time;"
        "os.write(1,b'PROG');time.sleep(.05);"
        "os.write(1,b'RESS: 4/10\\r');time.sleep(.05)"
    )
    manifest, queue = prepare_manifest(
        tmp_path,
        [sys.executable, "-c", script],
        mode=ProgressMode.REGEX,
        pattern=r"^PROGRESS: ([0-9]+)/([0-9]+)$",
    )
    try:
        assert run_with_handoff(manifest) == 0
    finally:
        os.environ.pop("RUNBUOY_HOME")
    rows = queue.event_rows("0190f2a0-a003-7abc-8def-0123456789ab")
    events = [json.loads(row["event_json"]) for row in rows]
    progress = [event for event in events if event["type"] == "run.progress"]
    assert progress[0]["payload"]["progress"]["fraction"] == 0.4


def test_worker_nonzero_exit_is_failed(tmp_path: Path) -> None:
    manifest, queue = prepare_manifest(tmp_path, ["/bin/sh", "-c", "exit 3"])
    try:
        assert run_with_handoff(manifest) == 3
    finally:
        os.environ.pop("RUNBUOY_HOME")
    run = queue.get_run("0190f2a0-a003-7abc-8def-0123456789ab")
    assert run is not None
    assert run["status"] == "FAILED"
    assert run["exit_code"] == 3


def test_worker_does_not_start_target_without_cli_ack(tmp_path: Path) -> None:
    sentinel = tmp_path / "must-not-exist"
    manifest_path, queue = prepare_manifest(
        tmp_path,
        [sys.executable, "-c", f"from pathlib import Path;Path({str(sentinel)!r}).touch()"],
    )
    manifest = RunManifest.model_validate_json(manifest_path.read_text())
    manifest = manifest.model_copy(update={"handoff_timeout_seconds": 1})
    manifest.write_securely(manifest_path)
    try:
        assert run_worker(manifest_path) == 125
    finally:
        os.environ.pop("RUNBUOY_HOME")

    assert not sentinel.exists()
    run = queue.get_run(manifest.run_id)
    assert run is not None
    assert run["status"] == "LOST"
    assert run["started_at"] is None


def test_worker_builds_progress_adapter_before_target(tmp_path: Path) -> None:
    sentinel = tmp_path / "must-not-exist"
    manifest_path, queue = prepare_manifest(
        tmp_path,
        [sys.executable, "-c", f"from pathlib import Path;Path({str(sentinel)!r}).touch()"],
        mode=ProgressMode.REGEX,
        pattern="(",
    )
    try:
        assert run_worker(manifest_path) == 125
    finally:
        os.environ.pop("RUNBUOY_HOME")

    assert not sentinel.exists()
    run = queue.get_run("0190f2a0-a003-7abc-8def-0123456789ab")
    assert run is not None
    assert run["status"] == "LOST"
    assert run["started_at"] is None


def test_worker_reports_popen_failure_after_ack(tmp_path: Path) -> None:
    manifest_path, queue = prepare_manifest(tmp_path, ["/runbuoy/does-not-exist"])
    try:
        assert run_with_handoff(manifest_path) == 127
    finally:
        os.environ.pop("RUNBUOY_HOME")

    run = queue.get_run("0190f2a0-a003-7abc-8def-0123456789ab")
    assert run is not None
    assert run["status"] == "FAILED"
    assert run["started_at"] is None
