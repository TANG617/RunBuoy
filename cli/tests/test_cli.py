from __future__ import annotations

import json
import shutil
import sys
import time
from pathlib import Path

import pytest
from typer.testing import CliRunner

from runbuoy.cli.app import app
from runbuoy.pairing import flow

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
    assert requested == ["http://127.0.0.1:8000/healthz"]
    assert json.loads(result.stdout)["checks"]["server_reachable"] is True


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
    result = runner.invoke(app, ["pair", "--json", "--no-wait"])
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
    payloads = [json.loads(line) for line in result.stdout.splitlines()]
    run_id = payloads[0]["run_id"]
    assert payloads[-1]["result"]["status"] == "SUCCEEDED"
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
