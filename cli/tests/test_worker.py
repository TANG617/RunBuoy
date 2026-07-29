from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any

from runbuoy.config import Config, ephemeral_token, save_config
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
    os.environ["RUNBUOY_DISABLE_KEYRING"] = "1"
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


def test_worker_captures_real_exit_and_final_result(tmp_path: Path) -> None:
    manifest, queue = prepare_manifest(
        tmp_path,
        [sys.executable, "-c", "print('safe local output')"],
    )
    try:
        assert run_worker(manifest) == 0
    finally:
        os.environ.pop("RUNBUOY_HOME")
        os.environ.pop("RUNBUOY_DISABLE_KEYRING")
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
        assert run_worker(manifest) == 0
    finally:
        os.environ.pop("RUNBUOY_HOME")
        os.environ.pop("RUNBUOY_DISABLE_KEYRING")
    rows = queue.event_rows("0190f2a0-a003-7abc-8def-0123456789ab")
    events = [json.loads(row["event_json"]) for row in rows]
    progress = [event for event in events if event["type"] == "run.progress"]
    assert progress[0]["payload"]["progress"]["fraction"] == 0.4


def test_worker_nonzero_exit_is_failed(tmp_path: Path) -> None:
    manifest, queue = prepare_manifest(tmp_path, ["/bin/sh", "-c", "exit 3"])
    try:
        assert run_worker(manifest) == 3
    finally:
        os.environ.pop("RUNBUOY_HOME")
        os.environ.pop("RUNBUOY_DISABLE_KEYRING")
    run = queue.get_run("0190f2a0-a003-7abc-8def-0123456789ab")
    assert run is not None
    assert run["status"] == "FAILED"
    assert run["exit_code"] == 3


def _enable_test_delivery(tmp_path: Path, *, retry_window: float) -> None:
    paths = AppPaths(
        tmp_path / "config",
        tmp_path / "data",
        tmp_path / "state",
        tmp_path / "cache",
    )
    save_config(
        paths,
        Config(
            upload_interval_seconds=0.1,
            request_timeout_seconds=1,
            terminal_retry_window_seconds=retry_window,
        ),
    )
    credentials = paths.credential_file
    credentials.write_text('{"machine_credential":"paired"}', encoding="utf-8")
    credentials.chmod(0o600)


def test_worker_retries_terminal_delivery_after_target_exit(
    tmp_path: Path, monkeypatch: Any
) -> None:
    manifest, queue = prepare_manifest(tmp_path, ["/bin/sh", "-c", "exit 0"])
    _enable_test_delivery(tmp_path, retry_window=2)

    class Client:
        terminal_attempts = 0

        def __init__(self, _config: object, _credentials: object) -> None:
            pass

        def update_machine(self, _machine_id: str, _display_name: str) -> None:
            pass

        def upsert_run(self, _run: dict[str, object]) -> None:
            pass

        def upload_events(self, _run_id: str, events: list[Any]) -> None:
            if any(event.type == "run.succeeded" for event in events):
                Client.terminal_attempts += 1
                if Client.terminal_attempts == 1:
                    raise OSError("temporarily offline")

        def close(self) -> None:
            pass

    monkeypatch.setattr("runbuoy.worker.runtime.RemoteClient", Client)
    try:
        assert run_worker(manifest) == 0
    finally:
        os.environ.pop("RUNBUOY_HOME")
        os.environ.pop("RUNBUOY_DISABLE_KEYRING")

    assert Client.terminal_attempts == 2
    assert queue.pending_event_count() == 0


def test_worker_preserves_terminal_delivery_after_retry_window(
    tmp_path: Path, monkeypatch: Any
) -> None:
    manifest, queue = prepare_manifest(tmp_path, ["/bin/sh", "-c", "exit 0"])
    _enable_test_delivery(tmp_path, retry_window=0.1)

    class Client:
        def __init__(self, _config: object, _credentials: object) -> None:
            pass

        def update_machine(self, _machine_id: str, _display_name: str) -> None:
            pass

        def upsert_run(self, _run: dict[str, object]) -> None:
            pass

        def upload_events(self, _run_id: str, _events: list[Any]) -> None:
            raise OSError("still offline")

        def close(self) -> None:
            pass

    monkeypatch.setattr("runbuoy.worker.runtime.RemoteClient", Client)
    started = time.monotonic()
    try:
        assert run_worker(manifest) == 0
    finally:
        os.environ.pop("RUNBUOY_HOME")
        os.environ.pop("RUNBUOY_DISABLE_KEYRING")

    assert time.monotonic() - started < 1
    assert queue.pending_event_count() > 0
