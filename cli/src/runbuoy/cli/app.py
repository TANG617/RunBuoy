from __future__ import annotations

import json
import os
import platform
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import typer
from pydantic import ValidationError
from rich.console import Console
from rich.table import Table

from runbuoy import __version__, sdk
from runbuoy.config import Config, CredentialStore, ephemeral_token, load_config, save_config
from runbuoy.executors.tmux import TmuxExecutor
from runbuoy.ids import uuid7
from runbuoy.models import ProgressMode, RunManifest
from runbuoy.networking.client import RemoteClient, flush_pending
from runbuoy.pairing.flow import pair_machine, public_pairing_fields
from runbuoy.paths import AppPaths
from runbuoy.persistence.store import EventQueue
from runbuoy.security.redaction import safe_message
from runbuoy.security.titles import safe_title
from runbuoy.worker.runtime import run_worker

app = typer.Typer(
    name="runbuoy",
    help="Keep every run in sight without exposing remote control.",
    no_args_is_help=True,
)
emit_app = typer.Typer(help="Emit a structured event to the current local Run.")
app.add_typer(emit_app, name="emit")
console = Console(stderr=True)


def _context() -> tuple[AppPaths, Config, CredentialStore, EventQueue]:
    paths = AppPaths.discover()
    paths.ensure()
    config = load_config(paths)
    return paths, config, CredentialStore(paths), EventQueue(paths.database)


def _json_print(value: Any) -> None:
    typer.echo(json.dumps(value, sort_keys=True, default=str))


def _flush_if_paired(config: Config, credentials: CredentialStore, queue: EventQueue) -> int:
    if credentials.get("machine_credential") is None:
        return 0
    client = RemoteClient(config, credentials)
    try:
        return flush_pending(queue, client, batch_size=config.batch_size)
    finally:
        client.close()


def _send_local(path: str, token: str, payload: dict[str, Any]) -> dict[str, Any]:
    request = {"token": token, **payload}
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(3)
        client.connect(path)
        client.sendall(json.dumps(request).encode() + b"\n")
        response = bytearray()
        while b"\n" not in response:
            chunk = client.recv(4096)
            if not chunk:
                break
            response.extend(chunk)
    return dict(json.loads(bytes(response).split(b"\n", 1)[0]))


@app.command(
    "run",
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)
def run_command(
    command: list[str] = typer.Argument(..., help="Command and arguments after --"),
    title: str | None = typer.Option(None, "--title"),
    progress_mode: ProgressMode = typer.Option(ProgressMode.INDETERMINATE, "--progress"),
    pattern: str | None = typer.Option(None, "--pattern"),
    total: float | None = typer.Option(None, "--total"),
    match: str | None = typer.Option(None, "--match"),
    unit: str | None = typer.Option(None, "--unit"),
    share_log_tail: int = typer.Option(0, "--share-log-tail", min=0, max=100),
    json_output: bool = typer.Option(False, "--json"),
    non_interactive: bool = typer.Option(False, "--non-interactive"),
    wait: bool = typer.Option(False, "--wait", help="Wait locally for the result"),
) -> None:
    """Start a persistent local tmux worker; target argv never enters remote payloads."""
    del non_interactive
    paths, config, credentials, queue = _context()
    if not command:
        raise typer.BadParameter("a command is required after --")
    if progress_mode == ProgressMode.LINES and (total is None or total <= 0):
        raise typer.BadParameter("--total > 0 is required for lines progress")
    if progress_mode == ProgressMode.REGEX and not pattern:
        raise typer.BadParameter("--pattern is required for regex progress")
    if total is not None and total <= 0:
        raise typer.BadParameter("--total must be greater than zero")
    machine_id = config.machine_id
    if machine_id is None:
        machine_id = f"machine_{uuid7().hex}"
        config = config.model_copy(update={"machine_id": machine_id})
        save_config(paths, config)
    run_id = str(uuid7())
    run_dir = paths.run_dir(run_id)
    manifest_path = run_dir / "manifest.json"
    log_path = run_dir / "run.log"
    result_path = run_dir / "result.json"
    socket_path = paths.event_socket(run_id)
    session = f"runbuoy-{run_id.replace('-', '')[:16]}"
    manifest = RunManifest(
        run_id=run_id,
        machine_id=machine_id,
        title=safe_title(command, title),
        argv=command,
        cwd=os.getcwd(),
        progress_mode=progress_mode,
        pattern=pattern,
        total=total,
        match=match,
        unit=unit,
        share_log_tail=share_log_tail,
        socket_path=str(socket_path),
        socket_token=ephemeral_token(),
        log_path=str(log_path),
        result_path=str(result_path),
        cancel_grace_seconds=config.cancel_grace_seconds,
    )
    manifest.write_securely(manifest_path)
    queue.create_run(
        run_id=run_id,
        machine_id=machine_id,
        title=manifest.title,
        manifest_path=str(manifest_path),
        log_path=str(log_path),
        result_path=str(result_path),
        socket_path=str(socket_path),
        tmux_session=session,
    )
    try:
        TmuxExecutor().start(session, manifest_path)
    except Exception as error:
        queue.append_event(
            run_id,
            "run.lost",
            {"termination_reason": "worker_start_failed", "message": safe_message(str(error))},
        )
        raise typer.BadParameter(str(error)) from error
    response = {
        "ok": True,
        "run_id": run_id,
        "title": manifest.title,
        "status": "STARTING",
        "local": {
            "status": f"runbuoy status {run_id}",
            "logs": f"runbuoy logs {run_id}",
            "attach": f"runbuoy attach {run_id}",
            "cancel": f"runbuoy cancel {run_id}",
        },
    }
    if json_output:
        _json_print(response)
    else:
        typer.echo(f"Run {run_id} started: {manifest.title}")
        typer.echo(f"Status: runbuoy status {run_id}")
    if wait:
        while not result_path.exists():
            time.sleep(0.1)
        result = json.loads(result_path.read_text(encoding="utf-8"))
        if json_output:
            _json_print({"ok": result["exit_code"] == 0, "result": result})
        raise typer.Exit(code=int(result["exit_code"]))
    _flush_if_paired(config, credentials, queue)


@app.command("list")
def list_runs(
    json_output: bool = typer.Option(False, "--json"),
    limit: int = typer.Option(20, "--limit", min=1, max=200),
) -> None:
    paths, config, credentials, queue = _context()
    del paths
    _flush_if_paired(config, credentials, queue)
    runs = queue.list_runs(limit)
    if json_output:
        _json_print({"runs": runs})
        return
    table = Table("Run ID", "Title", "Status", "Updated")
    for item in runs:
        table.add_row(item["run_id"], item["title"], item["status"], item["updated_at"])
    console.print(table)


@app.command()
def status(
    run_id: str,
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    _paths, config, credentials, queue = _context()
    _flush_if_paired(config, credentials, queue)
    item = queue.get_run(run_id)
    if item is None:
        raise typer.BadParameter(f"unknown run: {run_id}")
    if json_output:
        _json_print({"run": item})
    else:
        for key in ("run_id", "title", "status", "progress", "phase", "safe_message", "exit_code"):
            typer.echo(f"{key}: {item.get(key)}")


@app.command()
def logs(
    run_id: str,
    follow: bool = typer.Option(False, "--follow", "-f"),
    lines: int = typer.Option(200, "--lines", min=1, max=10_000),
) -> None:
    _paths, _config, _credentials, queue = _context()
    item = queue.get_run(run_id)
    if item is None:
        raise typer.BadParameter(f"unknown run: {run_id}")
    path = Path(item["log_path"])
    if not path.exists():
        raise typer.BadParameter("log has not been created yet")
    existing = path.read_text(encoding="utf-8", errors="replace").splitlines()[-lines:]
    typer.echo("\n".join(existing))
    if follow:
        subprocess.call(["tail", "-n", "0", "-f", str(path)])


@app.command()
def attach(run_id: str) -> None:
    _paths, _config, _credentials, queue = _context()
    item = queue.get_run(run_id)
    if item is None:
        raise typer.BadParameter(f"unknown run: {run_id}")
    session = item.get("tmux_session")
    if not session or not TmuxExecutor().exists(session):
        raise typer.BadParameter("local tmux session is no longer active")
    raise typer.Exit(TmuxExecutor().attach(session))


@app.command()
def cancel(
    run_id: str,
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    _paths, _config, _credentials, queue = _context()
    item = queue.get_run(run_id)
    if item is None:
        raise typer.BadParameter(f"unknown run: {run_id}")
    if item["status"] in {"SUCCEEDED", "FAILED", "CANCELLED", "LOST"}:
        raise typer.BadParameter(f"run is already {item['status']}")
    manifest = RunManifest.model_validate_json(
        Path(item["manifest_path"]).read_text(encoding="utf-8")
    )
    try:
        response = _send_local(manifest.socket_path, manifest.socket_token, {"kind": "cancel"})
    except OSError as error:
        raise typer.BadParameter("local worker is not reachable") from error
    if not response.get("ok"):
        raise typer.BadParameter(f"cancel rejected: {response.get('error')}")
    if json_output:
        _json_print({"ok": True, "run_id": run_id, "requested": "local_cancel"})
    else:
        typer.echo(f"Local cancellation requested for {run_id}")


@app.command()
def notify(
    title: str = typer.Option(..., "--title"),
    body: str = typer.Option(..., "--body"),
    subtitle: str | None = typer.Option(None, "--subtitle"),
    level: str = typer.Option("info", "--level"),
    field: list[str] | None = typer.Option(None, "--field", help="Repeat label=value"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    _paths, config, credentials, _queue = _context()
    if level not in {"info", "success", "warning", "error"}:
        raise typer.BadParameter("level must be info, success, warning, or error")
    fields: list[dict[str, str]] = []
    for raw in field or []:
        if "=" not in raw:
            raise typer.BadParameter("--field must be label=value")
        label, value = raw.split("=", 1)
        fields.append(
            {"label": safe_message(label, 80) or "", "value": safe_message(value, 300) or ""}
        )
    payload = {
        "title": safe_title(["notify"], title),
        "subtitle": safe_message(subtitle, 120),
        "body": safe_message(body, 2_000),
        "level": level,
        "fields": fields,
        "source": "cli",
        "machine_id": config.machine_id,
    }
    if credentials.get("machine_credential") is None:
        raise typer.BadParameter("not paired; run `runbuoy pair` first")
    client = RemoteClient(config, credentials)
    try:
        result = client.notify(payload)
    finally:
        client.close()
    if json_output:
        _json_print({"ok": True, "notification": result})
    else:
        typer.echo("Notification accepted")


@app.command()
def pair(
    no_wait: bool = typer.Option(False, "--no-wait"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    paths, config, credentials, _queue = _context()

    def show_created(created: dict[str, Any], qr_value: str) -> None:
        if json_output:
            _json_print({"ok": True, "state": "pending", "pairing": created, "qr": qr_value})
            return
        import qrcode

        qr = qrcode.QRCode(border=1)
        qr.add_data(qr_value)
        qr.print_ascii(invert=True)
        code = created.get("short_code") or created.get("challenge")
        typer.echo(f"Code: {code}")

    try:
        result, _qr_value = pair_machine(
            config,
            credentials,
            wait=not no_wait,
            on_created=show_created,
        )
    except Exception as error:
        raise typer.BadParameter(str(error)) from error
    machine_id = result.get("machine_id")
    if machine_id:
        config = config.model_copy(update={"machine_id": str(machine_id)})
        save_config(paths, config)
    safe_result = public_pairing_fields(result)
    if json_output and not no_wait:
        _json_print({"ok": True, "state": "paired", "pairing": safe_result})
    elif result.get("status") == "paired":
        typer.echo("Machine paired")


@app.command()
def doctor(json_output: bool = typer.Option(False, "--json")) -> None:
    _paths, config, credentials, queue = _context()
    checks: dict[str, Any] = {
        "cli_installed": True,
        "cli_version": __version__,
        "python_supported": sys.version_info >= (3, 12),
        "platform_supported": platform.system() in {"Darwin", "Linux"},
        "tmux_available": TmuxExecutor.available(),
        "paired": credentials.get("machine_credential") is not None,
        "server_reachable": False,
        "pending_events": len(queue.pending_events(100)),
    }
    try:
        import httpx

        response = httpx.get(str(config.server_url).rstrip("/") + "/healthz", timeout=2)
        checks["server_reachable"] = response.status_code < 500
    except Exception:
        pass
    required = ("python_supported", "platform_supported", "tmux_available")
    result = {"ok": all(checks[key] for key in required), "checks": checks}
    if json_output:
        _json_print(result)
    else:
        for key, value in checks.items():
            typer.echo(f"{key}: {value}")


@app.command()
def capabilities(json_output: bool = typer.Option(False, "--json")) -> None:
    progress_modes = [mode.value for mode in ProgressMode]
    result = {
        "schema_version": 1,
        "platforms": ["macos", "linux"],
        "progress_modes": progress_modes,
        "local_commands": ["list", "status", "logs", "attach", "cancel"],
        "remote_control": False,
        "inbound_tcp": False,
        "full_logs_uploaded_by_default": False,
    }
    if json_output:
        _json_print(result)
    else:
        typer.echo("Progress: " + ", ".join(progress_modes))
        typer.echo("Remote control: disabled")


@app.command("config")
def config_command(
    server_url: str | None = typer.Option(None, "--server-url"),
    machine_name: str | None = typer.Option(None, "--machine-name"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    paths, config, _credentials, _queue = _context()
    updates: dict[str, Any] = {}
    if server_url:
        updates["server_url"] = server_url
    if machine_name:
        updates["machine_name"] = safe_message(machine_name, 120)
    if updates:
        try:
            config = Config.model_validate({**config.model_dump(), **updates})
        except ValidationError as error:
            raise typer.BadParameter(str(error)) from error
        save_config(paths, config)
    result = {
        "server_url": str(config.server_url),
        "machine_id": config.machine_id,
        "machine_name": config.machine_name,
        "upload_interval_seconds": config.upload_interval_seconds,
        "batch_size": config.batch_size,
        "credential_storage": "keyring-or-mode-0600-fallback",
    }
    if json_output:
        _json_print(result)
    else:
        for key, value in result.items():
            typer.echo(f"{key}: {value}")


@emit_app.command("progress")
def emit_progress(
    current: float = typer.Option(..., "--current"),
    total: float = typer.Option(..., "--total"),
    unit: str | None = typer.Option(None, "--unit"),
    phase: str | None = typer.Option(None, "--phase"),
    message: str | None = typer.Option(None, "--message"),
) -> None:
    sdk.progress(current, total, unit=unit, phase=phase, message=message)


@emit_app.command("phase")
def emit_phase(value: str = typer.Argument(...)) -> None:
    sdk.phase(value)


@emit_app.command("message")
def emit_message(value: str = typer.Argument(...)) -> None:
    sdk.message(value)


@emit_app.command("attention")
def emit_attention(
    value: str = typer.Argument(...),
    status: str = typer.Option("ACTION_REQUIRED", "--status"),
) -> None:
    sdk.attention(value, status=status)


@app.command("_worker", hidden=True)
def worker_command(
    manifest: Path = typer.Option(..., "--manifest", exists=True, dir_okay=False),
) -> None:
    raise typer.Exit(run_worker(manifest))


def main() -> None:
    app()
