from __future__ import annotations

import json
import shutil
import sys
import time
from datetime import UTC, datetime, timedelta
from io import StringIO
from pathlib import Path

import pytest
from rich.console import Console
from typer.testing import CliRunner

from runbuoy.cli import app as cli_app
from runbuoy.cli.app import app
from runbuoy.config import Config, CredentialStore, save_config
from runbuoy.networking.client import RemoteError
from runbuoy.pairing import flow
from runbuoy.paths import AppPaths
from runbuoy.persistence.store import EventQueue

runner = CliRunner()


def test_capabilities_json_contract() -> None:
    result = runner.invoke(app, ["capabilities", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["schema_version"] == 2
    assert payload["remote_control"] is False
    assert payload["progress_modes"] == ["structured", "lines", "regex", "indeterminate"]


def test_doctor_uses_healthz(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RUNBUOY_HOME", str(tmp_path))
    monkeypatch.setenv("RUNBUOY_DISABLE_KEYRING", "1")
    credentials = tmp_path / "config" / "credentials.json"
    credentials.parent.mkdir(parents=True)
    credentials.write_text('{"machine_credential":"paired"}')
    credentials.chmod(0o600)
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
    payload = json.loads(result.stdout)
    assert payload["schema_version"] == 2
    assert payload["local_ready"] is True
    assert payload["delivery"] == {"paired": True, "reachable": True, "ready": True}


def test_doctor_local_readiness_does_not_require_pairing_or_delivery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RUNBUOY_HOME", str(tmp_path))
    monkeypatch.setenv("RUNBUOY_DISABLE_KEYRING", "1")
    monkeypatch.setattr(cli_app.TmuxExecutor, "available", staticmethod(lambda: True))
    monkeypatch.setattr("httpx.get", lambda *_args, **_kwargs: pytest.fail("must not call server"))

    default = runner.invoke(app, ["doctor", "--json"])
    required = runner.invoke(app, ["doctor", "--require-delivery", "--json"])

    assert default.exit_code == 0, default.output
    payload = json.loads(default.stdout)
    assert payload["local_ready"] is True
    assert payload["delivery"] == {"paired": False, "reachable": False, "ready": False}
    assert required.exit_code == 1
    assert not (tmp_path / "state").exists()


def test_delivery_diagnostics_cannot_break_local_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class BrokenCredentials:
        def get(self, _name: str) -> str | None:
            raise PermissionError("unsafe credential file")

    monkeypatch.setattr("httpx.get", lambda *_args, **_kwargs: pytest.fail("must not call server"))

    assert cli_app._delivery_status(cli_app.Config(), BrokenCredentials()) == {
        "paired": False,
        "reachable": False,
        "ready": False,
    }


@pytest.mark.parametrize(
    "arguments",
    [
        ["--progress", "regex", "--pattern", "("],
        ["--progress", "regex", "--pattern", "^([0-9]+)$"],
        ["--progress", "lines", "--total", "2", "--match", "("],
    ],
)
def test_run_rejects_invalid_progress_config_before_dry_run_side_effects(
    arguments: list[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RUNBUOY_HOME", str(tmp_path))
    result = runner.invoke(
        app,
        ["run", "--dry-run", "--json", *arguments, "--", sys.executable, "-c", "pass"],
    )

    assert result.exit_code != 0
    assert not (tmp_path / "state").exists()


def test_emit_cli_is_strict_outside_a_worker(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("RUNBUOY_EVENT_SOCKET", raising=False)
    monkeypatch.delenv("RUNBUOY_EVENT_TOKEN", raising=False)

    result = runner.invoke(app, ["emit", "phase", "Building"])

    assert result.exit_code == 1
    assert "not running under a RunBuoy Worker" in result.stderr


def test_run_checks_local_runtime_before_creating_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RUNBUOY_HOME", str(tmp_path))
    monkeypatch.setattr(cli_app.TmuxExecutor, "available", staticmethod(lambda: False))

    result = runner.invoke(
        app,
        ["run", "--json", "--", sys.executable, "-c", "raise SystemExit('must not run')"],
    )

    assert result.exit_code == 1
    assert json.loads(result.stderr)["error"]["code"] == "tmux_unavailable"
    assert not (tmp_path / "state").exists()


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


def test_device_unpair_revokes_server_before_deleting_local_credential(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RUNBUOY_HOME", str(tmp_path))
    monkeypatch.setenv("RUNBUOY_DISABLE_KEYRING", "1")
    paths = AppPaths.discover()
    config = Config(machine_id="machine_keep_identity")
    save_config(paths, config)
    credentials = CredentialStore(paths)
    credentials.set("machine_credential", "credential-delete-after-server")
    called: list[str] = []

    class Client:
        def __init__(self, supplied_config: Config, supplied_credentials: CredentialStore) -> None:
            assert supplied_config.machine_id == "machine_keep_identity"
            assert supplied_credentials.get("machine_credential") == (
                "credential-delete-after-server"
            )

        def revoke_machine_self(self, machine_id: str) -> None:
            assert credentials.get("machine_credential") is not None
            called.append(machine_id)

        def close(self) -> None:
            pass

    monkeypatch.setattr(cli_app, "RemoteClient", Client)
    result = runner.invoke(app, ["device", "unpair", "--yes", "--json"])

    assert result.exit_code == 0, result.output
    assert called == ["machine_keep_identity"]
    assert credentials.get("machine_credential") is None
    assert json.loads(paths.config_file.read_text())["machine_id"] == "machine_keep_identity"
    payload = json.loads(result.stdout)
    assert payload["server_revoked"] is True
    assert payload["local_runs_preserved"] is True


def test_device_unpair_server_failure_preserves_credential(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RUNBUOY_HOME", str(tmp_path))
    monkeypatch.setenv("RUNBUOY_DISABLE_KEYRING", "1")
    paths = AppPaths.discover()
    save_config(paths, Config(machine_id="machine_retry"))
    credentials = CredentialStore(paths)
    credentials.set("machine_credential", "must-survive")

    class Client:
        def __init__(self, _config: Config, _credentials: CredentialStore) -> None:
            pass

        def revoke_machine_self(self, _machine_id: str) -> None:
            raise RemoteError("server returned HTTP 503")

        def close(self) -> None:
            pass

    monkeypatch.setattr(cli_app, "RemoteClient", Client)
    result = runner.invoke(app, ["device", "unpair", "--yes", "--json"])

    assert result.exit_code == 1
    assert json.loads(result.stderr)["error"]["code"] == "server_revoke_failed"
    assert credentials.get("machine_credential") == "must-survive"


def test_device_unpair_local_only_warns_and_never_calls_server(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RUNBUOY_HOME", str(tmp_path))
    monkeypatch.setenv("RUNBUOY_DISABLE_KEYRING", "1")
    paths = AppPaths.discover()
    save_config(paths, Config(machine_id="machine_local_only"))
    credentials = CredentialStore(paths)
    credentials.set("machine_credential", "local-only")
    monkeypatch.setattr(
        cli_app,
        "RemoteClient",
        lambda *_args, **_kwargs: pytest.fail("must not contact Server"),
    )

    result = runner.invoke(
        app,
        ["device", "unpair", "--local-only", "--yes", "--json"],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["server_revoked"] is False
    assert "may remain valid" in payload["warning"]
    assert credentials.get("machine_credential") is None


def test_device_unpair_noninteractive_requires_yes_and_keeps_credential(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RUNBUOY_HOME", str(tmp_path))
    monkeypatch.setenv("RUNBUOY_DISABLE_KEYRING", "1")
    paths = AppPaths.discover()
    save_config(paths, Config(machine_id="machine_confirm"))
    credentials = CredentialStore(paths)
    credentials.set("machine_credential", "confirmation-required")

    result = runner.invoke(app, ["device", "unpair", "--json"])

    assert result.exit_code == 1
    assert json.loads(result.stderr)["error"]["code"] == "confirmation_required"
    assert credentials.get("machine_credential") == "confirmation-required"


@pytest.mark.tmux
@pytest.mark.integration
@pytest.mark.skipif(shutil.which("tmux") is None, reason="tmux is not installed")
def test_tmux_run_success_line_progress_and_local_commands(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RUNBUOY_HOME", str(tmp_path))
    monkeypatch.setenv("RUNBUOY_DISABLE_KEYRING", "1")
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
def test_detached_handoff_accepts_an_instantly_completed_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RUNBUOY_HOME", str(tmp_path))
    monkeypatch.setenv("RUNBUOY_DISABLE_KEYRING", "1")

    start = runner.invoke(
        app,
        ["run", "--json", "--", sys.executable, "-c", "pass"],
    )

    assert start.exit_code == 0, start.output
    payload = json.loads(start.stdout)
    assert payload["detached"] is True
    assert payload["worker_ready"] is True
    assert payload["status"] in {"RUNNING", "SUCCEEDED"}
    run_id = payload["run_id"]
    for _attempt in range(100):
        status = json.loads(runner.invoke(app, ["status", run_id, "--json"]).stdout)
        if status["run"]["status"] == "SUCCEEDED":
            break
        time.sleep(0.02)
    assert status["run"]["status"] == "SUCCEEDED"


@pytest.mark.tmux
@pytest.mark.integration
@pytest.mark.skipif(shutil.which("tmux") is None, reason="tmux is not installed")
def test_local_cancel_uses_socket_and_reaches_cancelled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RUNBUOY_HOME", str(tmp_path))
    monkeypatch.setenv("RUNBUOY_DISABLE_KEYRING", "1")
    start = runner.invoke(
        app,
        ["run", "--json", "--", sys.executable, "-c", "import time;time.sleep(30)"],
    )
    assert start.exit_code == 0, start.output
    start_payload = json.loads(start.stdout)
    assert start_payload["detached"] is True
    assert start_payload["worker_ready"] is True
    assert start_payload["status"] == "RUNNING"
    run_id = start_payload["run_id"]
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


@pytest.mark.tmux
@pytest.mark.integration
@pytest.mark.skipif(shutil.which("tmux") is None, reason="tmux is not installed")
def test_paired_but_unreachable_keeps_local_run_and_control_available(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RUNBUOY_HOME", str(tmp_path))
    monkeypatch.setenv("RUNBUOY_DISABLE_KEYRING", "1")
    config = tmp_path / "config" / "config.json"
    config.parent.mkdir(parents=True)
    config.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "machine_id": "machine-local",
                "server_url": "http://127.0.0.1:9",
            }
        )
    )
    credentials = tmp_path / "config" / "credentials.json"
    credentials.write_text('{"machine_credential":"paired"}')
    credentials.chmod(0o600)

    start = runner.invoke(
        app,
        ["run", "--json", "--", sys.executable, "-c", "import time;time.sleep(30)"],
    )

    assert start.exit_code == 0, start.output
    payload = json.loads(start.stdout)
    assert payload["worker_ready"] is True
    assert payload["delivery"] == {"paired": True, "reachable": False, "ready": False}
    run_id = payload["run_id"]
    queue = EventQueue(tmp_path / "state" / "runbuoy.sqlite3")
    item = queue.get_run(run_id)
    assert item is not None
    assert item["status"] == "RUNNING"
    assert cli_app.TmuxExecutor().exists(str(item["tmux_session"]))
    assert payload["local"]["attach"] == f"runbuoy attach {run_id}"

    cancelled = runner.invoke(app, ["cancel", run_id, "--json"])
    assert cancelled.exit_code == 0, cancelled.output
    for _attempt in range(100):
        item = queue.get_run(run_id)
        if item is not None and item["status"] == "CANCELLED":
            break
        time.sleep(0.05)
    assert item is not None
    assert item["status"] == "CANCELLED"


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


def test_status_shows_progress_and_healthy_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RUNBUOY_HOME", str(tmp_path))
    queue = EventQueue(tmp_path / "state" / "runbuoy.sqlite3")
    run_id = "019c2345-6789-7000-8000-000000000001"
    _create_local_run(queue, tmp_path, run_id, title="Visible progress", terminal=False)
    queue.append_event(
        run_id,
        "run.progress",
        {
            "progress": {"current": 42, "total": 100, "fraction": 0.42},
            "phase": "Building",
            "message": "Optimizing assets",
        },
    )

    result = runner.invoke(app, ["status", run_id])

    assert result.exit_code == 0, result.output
    assert "Health" in result.stdout
    assert "Healthy" in result.stdout
    assert "42%" in result.stdout
    assert "Optimizing assets" in result.stdout


def test_status_display_renders_rich_progress_bar() -> None:
    now = datetime.now(UTC)
    item = {
        "run_id": "019c3456-789a-7000-8000-000000000001",
        "title": "Rich status",
        "status": "RUNNING",
        "progress": {"current": 42, "total": 100, "fraction": 0.42},
        "phase": "Building",
        "safe_message": "Optimizing assets",
        "exit_code": None,
        "started_at": (now - timedelta(minutes=1)).isoformat(),
        "updated_at": now.isoformat(),
        "ended_at": None,
    }
    output = StringIO()
    render_console = Console(
        file=output,
        force_terminal=True,
        color_system=None,
        width=100,
    )

    render_console.print(cli_app._StatusDisplay(item, display_console=render_console))

    rendered = output.getvalue()
    assert "RunBuoy · Rich status" in rendered
    assert "Healthy" in rendered
    assert "42%" in rendered
    assert "━" in rendered

    indeterminate_output = StringIO()
    indeterminate_console = Console(
        file=indeterminate_output,
        force_terminal=True,
        color_system=None,
        width=100,
    )
    indeterminate_console.print(
        cli_app._StatusDisplay(
            {**item, "progress": None},
            display_console=indeterminate_console,
        )
    )
    indeterminate = indeterminate_output.getvalue()
    assert "Progress" in indeterminate
    assert "━" in indeterminate
    assert "%" not in indeterminate


def test_health_state_becomes_stale_after_heartbeat_window() -> None:
    now = datetime(2026, 8, 5, 12, 0, tzinfo=UTC)
    active = {
        "status": "RUNNING",
        "updated_at": (now - timedelta(seconds=59)).isoformat(),
    }
    stale = {
        "status": "RUNNING",
        "updated_at": (now - timedelta(seconds=60)).isoformat(),
    }
    lost = {"status": "LOST", "updated_at": now.isoformat()}

    assert cli_app._health_state(active, now=now)[0] == "HEALTHY"
    assert cli_app._health_state(stale, now=now)[0] == "STALE"
    assert cli_app._health_state(lost, now=now)[0] == "OFFLINE"


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


def test_region_selects_hosted_server_and_is_locked_after_pairing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RUNBUOY_HOME", str(tmp_path))
    monkeypatch.setenv("RUNBUOY_DISABLE_KEYRING", "1")

    selected = runner.invoke(app, ["config", "set", "--region", "cn", "--json"])
    assert selected.exit_code == 0, selected.output
    payload = json.loads(selected.stdout)
    assert payload["region"] == "cn"
    assert payload["server_url"] == "https://api-cn.runbuoy.cloud/"

    config_file = tmp_path / "config" / "config.json"
    saved_config = json.loads(config_file.read_text())
    saved_config["machine_id"] = "machine_a"
    config_file.write_text(json.dumps(saved_config))
    credential_file = tmp_path / "config" / "credentials.json"
    credential_file.write_text('{"machine_credential":"paired"}')
    credential_file.chmod(0o600)
    rejected = runner.invoke(app, ["config", "set", "--region", "global"])
    assert rejected.exit_code != 0
    assert "cannot be changed after pairing" in rejected.output


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


def test_sync_replays_all_pending_runs_under_one_local_drainer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RUNBUOY_HOME", str(tmp_path))
    monkeypatch.setenv("RUNBUOY_DISABLE_KEYRING", "1")
    credentials = tmp_path / "config" / "credentials.json"
    credentials.parent.mkdir(parents=True)
    credentials.write_text('{"machine_credential":"paired"}')
    credentials.chmod(0o600)
    queue = EventQueue(tmp_path / "state" / "runbuoy.sqlite3")
    for run_id in ("run-a", "run-b"):
        queue.create_run(
            run_id=run_id,
            machine_id="machine-local",
            title="Safe run",
            manifest_path=str(tmp_path / run_id / "manifest.json"),
            log_path=str(tmp_path / run_id / "run.log"),
            result_path=str(tmp_path / run_id / "result.json"),
            socket_path=str(tmp_path / run_id / "event.sock"),
            tmux_session=None,
        )
    uploaded: list[str] = []

    class Client:
        def __init__(self, _config: object, _credentials: object) -> None:
            pass

        def update_machine(self, _machine_id: str, _display_name: str) -> None:
            pass

        def upsert_run(self, run: dict[str, object]) -> None:
            uploaded.append(str(run["run_id"]))

        def upload_events(self, _run_id: str, _events: list[object]) -> None:
            pass

        def close(self) -> None:
            pass

    monkeypatch.setattr(cli_app, "RemoteClient", Client)
    result = runner.invoke(app, ["sync", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["server_accepted_events"] == 2
    assert set(uploaded) == {"run-a", "run-b"}
    assert queue.pending_event_count() == 0


def test_sync_without_pairing_keeps_local_outbox(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RUNBUOY_HOME", str(tmp_path))
    monkeypatch.setenv("RUNBUOY_DISABLE_KEYRING", "1")
    queue = EventQueue(tmp_path / "state" / "runbuoy.sqlite3")
    queue.create_run(
        run_id="run-local",
        machine_id="machine-local",
        title="Safe run",
        manifest_path="manifest",
        log_path="log",
        result_path="result",
        socket_path="socket",
        tmux_session=None,
    )

    result = runner.invoke(app, ["sync", "--json"])

    assert result.exit_code == 1
    assert json.loads(result.stderr)["error"]["code"] == "not_paired"
    assert queue.pending_event_count() == 1


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


def test_notify_unpaired_supports_only_dry_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RUNBUOY_HOME", str(tmp_path))
    monkeypatch.setenv("RUNBUOY_DISABLE_KEYRING", "1")
    arguments = ["notify", "--title", "Safe", "--body", "Preview", "--json"]

    preview = runner.invoke(app, [*arguments, "--dry-run"])
    real = runner.invoke(app, arguments)

    assert preview.exit_code == 0
    assert json.loads(preview.stdout)["dry_run"] is True
    assert real.exit_code == 1
    assert json.loads(real.stderr)["error"]["code"] == "not_paired"


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
    assert captured["live_activity"] == cli_app.LiveActivityPolicy.IMMEDIATE
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
