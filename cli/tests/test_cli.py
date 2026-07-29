from __future__ import annotations

import json
import shutil
import sys
import time
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from runbuoy.cli import app as cli_app
from runbuoy.cli.app import app
from runbuoy.pairing import flow
from runbuoy.persistence.store import EventQueue

runner = CliRunner()


def test_capabilities_json_contract() -> None:
    result = runner.invoke(app, ["capabilities", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["schema_version"] == 1
    assert payload["remote_control"] is False
    assert payload["progress_modes"] == ["structured", "lines", "regex", "indeterminate"]


def test_doctor_uses_healthz(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RUNBUOY_HOME", str(tmp_path))
    requested: list[str] = []

    class Response:
        status_code = 200

    def get(url: str, *, timeout: float) -> Response:
        assert timeout == 2
        requested.append(url)
        return Response()

    monkeypatch.setattr("httpx.get", get)
    result = runner.invoke(app, ["doctor", "--json"])
    assert result.exit_code == 0
    assert requested == ["https://api.runbuoy.cloud/healthz"]
    assert json.loads(result.stdout)["checks"]["server_reachable"] is True


def _prepare_doctor_repair(tmp_path: Path) -> EventQueue:
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True)
    credentials = config_dir / "credentials.json"
    credentials.write_text('{"machine_credential":"paired"}', encoding="utf-8")
    credentials.chmod(0o600)
    queue = EventQueue(tmp_path / "state" / "runbuoy.sqlite3")
    run_id = "019cdddd-0000-7000-8000-000000000001"
    queue.create_run(
        run_id=run_id,
        machine_id="machine-local",
        title="Repair terminal delivery",
        manifest_path=str(tmp_path / "manifest.json"),
        log_path=str(tmp_path / "run.log"),
        result_path=str(tmp_path / "result.json"),
        socket_path=str(tmp_path / "event.sock"),
        tmux_session=None,
    )
    with queue.connect() as connection:
        connection.execute("UPDATE events SET delivered = 1")
    queue.append_event(run_id, "run.cancelled", {"exit_code": 130})
    with queue.connect() as connection:
        connection.execute("UPDATE events SET next_attempt_at = ?", (9_999_999_999,))
    return queue


def test_doctor_repair_delivers_terminal_pending(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RUNBUOY_HOME", str(tmp_path))
    monkeypatch.setenv("RUNBUOY_DISABLE_KEYRING", "1")
    queue = _prepare_doctor_repair(tmp_path)
    uploaded: list[str] = []

    class Response:
        status_code = 200

    class Client:
        def __init__(self, _config: object, _credentials: object) -> None:
            pass

        def update_machine(self, _machine_id: str, _display_name: str) -> None:
            pass

        def upsert_run(self, _run: dict[str, object]) -> None:
            pass

        def upload_events(self, _run_id: str, events: list[Any]) -> None:
            uploaded.extend(event.type for event in events)

        def close(self) -> None:
            pass

    monkeypatch.setattr("httpx.get", lambda *_args, **_kwargs: Response())
    monkeypatch.setattr(cli_app, "RemoteClient", Client)

    result = runner.invoke(app, ["doctor", "--repair", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert uploaded == ["run.cancelled"]
    assert payload["repair"]["completed"] is True
    assert payload["repair"]["delivered_events"] == 1
    assert payload["checks"]["pending_events"] == 0
    assert payload["checks"]["pending_terminal_events"] == 0
    assert queue.pending_event_count() == 0


def test_doctor_repair_failure_keeps_pending_and_exits_nonzero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RUNBUOY_HOME", str(tmp_path))
    monkeypatch.setenv("RUNBUOY_DISABLE_KEYRING", "1")
    queue = _prepare_doctor_repair(tmp_path)

    class Response:
        status_code = 200

    class Client:
        def __init__(self, _config: object, _credentials: object) -> None:
            pass

        def update_machine(self, _machine_id: str, _display_name: str) -> None:
            pass

        def upsert_run(self, _run: dict[str, object]) -> None:
            pass

        def upload_events(self, _run_id: str, _events: list[object]) -> None:
            raise OSError("offline")

        def close(self) -> None:
            pass

    monkeypatch.setattr("httpx.get", lambda *_args, **_kwargs: Response())
    monkeypatch.setattr(cli_app, "RemoteClient", Client)

    result = runner.invoke(app, ["doctor", "--repair", "--json"])

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["repair"]["completed"] is False
    assert payload["repair"]["pending_events_after"] == 1
    assert payload["checks"]["last_delivery_error"] == "offline"
    assert queue.pending_event_count() == 1


def test_pair_json_never_prints_exchange_secret(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RUNBUOY_HOME", str(tmp_path))
    monkeypatch.setenv("RUNBUOY_DISABLE_KEYRING", "1")

    class Client:
        def __init__(self, _config: object, _credentials: object) -> None:
            pass

        def create_pairing(self, payload: object) -> dict[str, str]:
            assert isinstance(payload, dict)
            machine_id = payload.get("machine_id")
            assert isinstance(machine_id, str)
            assert machine_id.startswith("machine_")
            return {
                "pairing_session_id": "pair-safe",
                "challenge": "challenge-safe-value",
                "short_code": "123456",
                "exchange_secret": "rbx-NEVER-PRINT",
                "api_token": "token-NEVER-PRINT",
            }

        def close(self) -> None:
            pass

    monkeypatch.setattr(flow, "RemoteClient", Client)
    result = runner.invoke(app, ["device", "pair", "--json", "--no-wait"])
    assert result.exit_code == 0, result.output
    assert "rbx-NEVER-PRINT" not in result.stdout
    assert "token-NEVER-PRINT" not in result.stdout
    assert "exchange_secret" not in result.stdout
    assert json.loads(result.stdout)["state"] == "pending"
    config = json.loads((tmp_path / "config" / "config.json").read_text())
    assert config["machine_id"].startswith("machine_")


@pytest.mark.tmux
@pytest.mark.integration
@pytest.mark.skipif(shutil.which("tmux") is None, reason="tmux is not installed")
def test_tmux_run_success_line_progress_and_local_commands(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RUNBUOY_HOME", str(tmp_path))
    command = "print('DONE');print('DONE')"
    result = runner.invoke(
        app,
        [
            "run",
            "--json",
            "--wait",
            "--progress",
            "lines",
            "--total",
            "2",
            "--match",
            "^DONE$",
            "--",
            sys.executable,
            "-c",
            command,
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    run_id = payload["run_id"]
    assert payload["result"]["status"] == "SUCCEEDED"
    status_result = runner.invoke(app, ["status", run_id, "--json"])
    assert status_result.exit_code == 0
    status_payload = json.loads(status_result.stdout)
    assert status_payload["run"]["progress"]["fraction"] == 1
    log_result = runner.invoke(app, ["logs", run_id])
    assert log_result.exit_code == 0
    assert log_result.stdout.count("DONE") == 2


@pytest.mark.tmux
@pytest.mark.integration
@pytest.mark.skipif(shutil.which("tmux") is None, reason="tmux is not installed")
def test_local_cancel_uses_socket_and_reaches_cancelled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RUNBUOY_HOME", str(tmp_path))
    start = runner.invoke(
        app,
        ["run", "--json", "--", sys.executable, "-c", "import time;time.sleep(30)"],
    )
    assert start.exit_code == 0, start.output
    run_id = json.loads(start.stdout)["run_id"]
    for _attempt in range(50):
        status = json.loads(runner.invoke(app, ["status", run_id, "--json"]).stdout)
        if status["run"]["status"] == "RUNNING":
            break
        time.sleep(0.05)
    cancelled = runner.invoke(app, ["cancel", run_id, "--json"])
    assert cancelled.exit_code == 0, cancelled.output
    for _attempt in range(100):
        status = json.loads(runner.invoke(app, ["status", run_id, "--json"]).stdout)
        if status["run"]["status"] == "CANCELLED":
            break
        time.sleep(0.05)
    assert status["run"]["status"] == "CANCELLED"


def _create_local_run(
    queue: EventQueue,
    tmp_path: Path,
    run_id: str,
    *,
    title: str,
    terminal: bool,
) -> None:
    queue.create_run(
        run_id=run_id,
        machine_id="machine-local",
        title=title,
        manifest_path=str(tmp_path / run_id / "manifest.json"),
        log_path=str(tmp_path / run_id / "run.log"),
        result_path=str(tmp_path / run_id / "result.json"),
        socket_path=str(tmp_path / run_id / "event.sock"),
        tmux_session=f"runbuoy-{run_id}",
    )
    queue.append_event(run_id, "run.started", {"message": "Run started"})
    if terminal:
        queue.append_event(run_id, "run.succeeded", {"exit_code": 0})


def test_list_defaults_to_active_and_all_includes_history(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RUNBUOY_HOME", str(tmp_path))
    queue = EventQueue(tmp_path / "state" / "runbuoy.sqlite3")
    active_id = "019c0000-0000-7000-8000-000000000001"
    history_id = "019c0000-0000-7000-8000-000000000002"
    _create_local_run(queue, tmp_path, active_id, title="Active run", terminal=False)
    _create_local_run(queue, tmp_path, history_id, title="History run", terminal=True)

    active = runner.invoke(app, ["list", "--json"])
    assert active.exit_code == 0, active.output
    assert [item["run_id"] for item in json.loads(active.stdout)["runs"]] == [active_id]

    all_runs = runner.invoke(app, ["list", "--all", "--json"])
    assert all_runs.exit_code == 0, all_runs.output
    assert {item["run_id"] for item in json.loads(all_runs.stdout)["runs"]} == {
        active_id,
        history_id,
    }
    assert "." not in json.loads(all_runs.stdout)["runs"][0]["updated_at"]


def test_local_list_never_constructs_a_remote_client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RUNBUOY_HOME", str(tmp_path))
    monkeypatch.setenv("RUNBUOY_DISABLE_KEYRING", "1")
    credentials = tmp_path / "config" / "credentials.json"
    credentials.parent.mkdir(parents=True)
    credentials.write_text('{"machine_credential":"paired"}')
    credentials.chmod(0o600)

    def unexpected_remote(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("list must not access the network")

    monkeypatch.setattr(cli_app, "RemoteClient", unexpected_remote)
    result = runner.invoke(app, ["list", "--json"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["runs"] == []


def test_unique_run_prefix_and_latest_are_accepted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RUNBUOY_HOME", str(tmp_path))
    queue = EventQueue(tmp_path / "state" / "runbuoy.sqlite3")
    run_id = "019c1234-5678-7000-8000-000000000001"
    _create_local_run(queue, tmp_path, run_id, title="Prefix run", terminal=False)

    by_prefix = runner.invoke(app, ["status", "019c1234", "--json"])
    assert by_prefix.exit_code == 0, by_prefix.output
    assert json.loads(by_prefix.stdout)["run"]["run_id"] == run_id

    latest = runner.invoke(app, ["status", "@latest", "--json"])
    assert latest.exit_code == 0, latest.output
    assert json.loads(latest.stdout)["run"]["run_id"] == run_id


def test_config_is_grouped_without_legacy_mutation_options(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RUNBUOY_HOME", str(tmp_path))
    changed = runner.invoke(
        app,
        [
            "config",
            "set",
            "--server-url",
            "https://example.runbuoy.dev",
            "--machine-name",
            "Build Mac",
            "--json",
        ],
    )
    assert changed.exit_code == 0, changed.output
    assert json.loads(changed.stdout)["machine_name"] == "Build Mac"

    legacy = runner.invoke(app, ["config", "--server-url", "https://legacy.invalid"])
    assert legacy.exit_code != 0


def test_paired_machine_name_change_syncs_immediately(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RUNBUOY_HOME", str(tmp_path))
    monkeypatch.setenv("RUNBUOY_DISABLE_KEYRING", "1")
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True)
    (config_dir / "config.json").write_text('{"machine_id":"machine_a","machine_name":"Old Mac"}')
    credentials = config_dir / "credentials.json"
    credentials.write_text('{"machine_credential":"paired"}')
    credentials.chmod(0o600)
    updates: list[tuple[str, str]] = []

    class Client:
        def __init__(self, _config: object, _credentials: object) -> None:
            pass

        def update_machine(self, machine_id: str, display_name: str) -> None:
            updates.append((machine_id, display_name))

        def close(self) -> None:
            pass

    monkeypatch.setattr(cli_app, "RemoteClient", Client)
    result = runner.invoke(
        app,
        ["config", "set", "--machine-name", "Build Mac", "--json"],
    )

    assert result.exit_code == 0, result.output
    assert updates == [("machine_a", "Build Mac")]
    queue = EventQueue(tmp_path / "state" / "runbuoy.sqlite3")
    assert queue.pending_machine_metadata() is None


def test_offline_machine_name_change_is_saved_and_queued(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RUNBUOY_HOME", str(tmp_path))
    monkeypatch.setenv("RUNBUOY_DISABLE_KEYRING", "1")
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True)
    (config_dir / "config.json").write_text('{"machine_id":"machine_a","machine_name":"Old Mac"}')
    credentials = config_dir / "credentials.json"
    credentials.write_text('{"machine_credential":"paired"}')
    credentials.chmod(0o600)

    class Client:
        def __init__(self, _config: object, _credentials: object) -> None:
            pass

        def update_machine(self, _machine_id: str, _display_name: str) -> None:
            raise OSError("offline")

        def close(self) -> None:
            pass

    monkeypatch.setattr(cli_app, "RemoteClient", Client)
    result = runner.invoke(
        app,
        ["config", "set", "--machine-name", "Build Mac", "--json"],
    )

    assert result.exit_code == 1
    assert json.loads(result.stderr)["error"]["code"] == "machine_name_sync_pending"
    saved = json.loads((config_dir / "config.json").read_text())
    assert saved["machine_name"] == "Build Mac"
    queue = EventQueue(tmp_path / "state" / "runbuoy.sqlite3")
    pending = queue.pending_machine_metadata(now=time.time() + 2)
    assert pending is not None
    assert pending["display_name"] == "Build Mac"


def test_run_dry_run_separates_remote_and_local_fields(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RUNBUOY_HOME", str(tmp_path))
    result = runner.invoke(
        app,
        ["run", "--dry-run", "--json", "--title", "Safe title", "--", "python", "secret.py"],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["remote"]["title"] == "Safe title"
    assert payload["local_only"]["argv"] == ["python", "secret.py"]
    assert not (tmp_path / "state").exists()


def test_demo_notification_uses_ready_made_payload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RUNBUOY_HOME", str(tmp_path))
    monkeypatch.setenv("RUNBUOY_DISABLE_KEYRING", "1")
    credentials = tmp_path / "config" / "credentials.json"
    credentials.parent.mkdir(parents=True)
    credentials.write_text('{"machine_credential":"paired"}')
    credentials.chmod(0o600)
    sent: list[dict[str, object]] = []

    class Client:
        def __init__(self, _config: object, _credentials: object) -> None:
            pass

        def notify(self, payload: dict[str, object]) -> dict[str, str]:
            sent.append(payload)
            return {"id": "notification-demo"}

        def close(self) -> None:
            pass

    monkeypatch.setattr(cli_app, "RemoteClient", Client)
    result = runner.invoke(app, ["demo", "notification", "--json"])
    assert result.exit_code == 0, result.output
    assert sent[0]["title"] == "RunBuoy test notification"
    assert json.loads(result.stdout)["accepted"] is True


def test_live_activity_demo_requires_pairing_before_start(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RUNBUOY_HOME", str(tmp_path))
    monkeypatch.setenv("RUNBUOY_DISABLE_KEYRING", "1")
    result = runner.invoke(app, ["demo", "live-activity", "--duration", "8", "--json"])
    assert result.exit_code == 1
    assert json.loads(result.stderr)["error"]["code"] == "not_paired"
    assert not (tmp_path / "state" / "runs").exists()


def test_live_activity_demo_builds_structured_demo_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RUNBUOY_HOME", str(tmp_path))
    monkeypatch.setenv("RUNBUOY_DISABLE_KEYRING", "1")
    credentials = tmp_path / "config" / "credentials.json"
    credentials.parent.mkdir(parents=True)
    credentials.write_text('{"machine_credential":"paired"}')
    credentials.chmod(0o600)
    captured: dict[str, object] = {}

    class Response:
        status_code = 200

    def fake_run_command(**kwargs: object) -> None:
        captured.update(kwargs)

    monkeypatch.setattr("httpx.get", lambda *_args, **_kwargs: Response())
    monkeypatch.setattr(cli_app, "run_command", fake_run_command)
    result = runner.invoke(
        app,
        [
            "demo",
            "live-activity",
            "--duration",
            "8",
            "--result",
            "failure",
            "--attention",
        ],
    )
    assert result.exit_code == 0, result.output
    assert captured["progress_mode"] == cli_app.ProgressMode.STRUCTURED
    assert captured["source"] == "demo"
    command = captured["command"]
    assert isinstance(command, list)
    assert "attention(" in command[2]
    assert "SystemExit(1)" in command[2]


def test_version_and_help_expose_new_workflow() -> None:
    version = runner.invoke(app, ["--version"])
    assert version.exit_code == 0
    assert version.stdout.startswith("runbuoy ")

    help_result = runner.invoke(app, ["--help"])
    assert help_result.exit_code == 0
    assert "demo" in help_result.stdout
    assert "device" in help_result.stdout
    assert "completion" in help_result.stdout
    assert "pair" not in {
        line.strip().split(maxsplit=1)[0]
        for line in help_result.stdout.splitlines()
        if line.strip().startswith("pair")
    }


def test_run_id_completion_reads_only_local_active_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RUNBUOY_HOME", str(tmp_path))
    queue = EventQueue(tmp_path / "state" / "runbuoy.sqlite3")
    active_id = "019caaaa-0000-7000-8000-000000000001"
    history_id = "019cbbbb-0000-7000-8000-000000000002"
    _create_local_run(queue, tmp_path, active_id, title="Active completion", terminal=False)
    _create_local_run(queue, tmp_path, history_id, title="Old completion", terminal=True)

    active = cli_app._complete_active_run("")
    assert [item.value for item in active] == [active_id]
    all_items = cli_app._complete_any_run("")
    assert {item.value for item in all_items} == {active_id, history_id}


def test_completion_script_uses_explicit_shell() -> None:
    result = runner.invoke(app, ["completion", "show", "zsh"])
    assert result.exit_code == 0, result.output
    assert "compdef" in result.stdout
    assert "_RUNBUOY_COMPLETE" in result.stdout


def test_history_prune_is_dry_run_by_default_when_requested_and_deletes_with_yes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RUNBUOY_HOME", str(tmp_path))
    queue = EventQueue(tmp_path / "state" / "runbuoy.sqlite3")
    run_id = "019cccc0-0000-7000-8000-000000000001"
    run_dir = tmp_path / "state" / "runs" / run_id
    run_dir.mkdir(parents=True)
    manifest = run_dir / "manifest.json"
    manifest.write_text("{}")
    queue.create_run(
        run_id=run_id,
        machine_id="machine-local",
        title="Old terminal run",
        manifest_path=str(manifest),
        log_path=str(run_dir / "run.log"),
        result_path=str(run_dir / "result.json"),
        socket_path=str(run_dir / "event.sock"),
        tmux_session=None,
    )
    queue.append_event(run_id, "run.succeeded", {"exit_code": 0})
    with queue.connect() as connection:
        connection.execute(
            "UPDATE runs SET ended_at = ?, updated_at = ? WHERE run_id = ?",
            ("2000-01-01T00:00:00+00:00", "2000-01-01T00:00:00+00:00", run_id),
        )

    protected = runner.invoke(
        app,
        ["history", "prune", "--older-than", "1m", "--dry-run", "--json"],
    )
    assert protected.exit_code == 0, protected.output
    assert json.loads(protected.stdout)["matched"] == 0

    preview = runner.invoke(
        app,
        [
            "history",
            "prune",
            "--older-than",
            "1m",
            "--include-unsynced",
            "--dry-run",
            "--json",
        ],
    )
    assert preview.exit_code == 0, preview.output
    assert json.loads(preview.stdout)["matched"] == 1
    assert queue.get_run(run_id) is not None
    assert run_dir.exists()

    removed = runner.invoke(
        app,
        [
            "history",
            "prune",
            "--older-than",
            "1m",
            "--include-unsynced",
            "--yes",
            "--json",
        ],
    )
    assert removed.exit_code == 0, removed.output
    assert json.loads(removed.stdout)["recoverable"] is False
    assert queue.get_run(run_id) is None
    assert not run_dir.exists()
