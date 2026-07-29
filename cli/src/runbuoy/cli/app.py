from __future__ import annotations

import json
import os
import platform
import re
import shlex
import shutil
import socket
import sqlite3
import subprocess
import sys
import time
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Any, NoReturn

import httpx
import typer
from pydantic import ValidationError
from rich.console import Console
from rich.table import Table
from typer._click.shell_completion import CompletionItem
from typer._completion_classes import completion_init
from typer._completion_shared import get_completion_script
from typer._completion_shared import install as install_completion

from runbuoy import __version__, sdk
from runbuoy.config import (
    Config,
    CredentialStore,
    ensure_machine_identity,
    ephemeral_token,
    load_config,
    save_config,
)
from runbuoy.executors.tmux import TmuxExecutor
from runbuoy.ids import uuid7
from runbuoy.models import ExecutionStatus, ProgressMode, RunManifest
from runbuoy.networking.client import RemoteClient, RemoteError, repair_pending
from runbuoy.pairing.flow import (
    PENDING_SESSION_KEY,
    pair_machine,
    public_pairing_fields,
    resume_pairing,
)
from runbuoy.paths import AppPaths
from runbuoy.persistence.store import TERMINAL_STATUSES, EventQueue
from runbuoy.security.redaction import safe_message
from runbuoy.security.titles import safe_title
from runbuoy.worker.runtime import run_worker

completion_init()


class NotificationLevel(StrEnum):
    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"


class AttentionStatus(StrEnum):
    INFORMATION = "INFORMATION"
    WARNING = "WARNING"
    ACTION_REQUIRED = "ACTION_REQUIRED"


class DemoResult(StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"


class CompletionShell(StrEnum):
    BASH = "bash"
    ZSH = "zsh"
    FISH = "fish"
    POWERSHELL = "powershell"
    PWSH = "pwsh"


app = typer.Typer(
    name="runbuoy",
    help="Keep local runs visible on iPhone without exposing remote control.",
    epilog=(
        "Quick start: run `runbuoy doctor`, `runbuoy device pair`, then "
        "`runbuoy demo live-activity`."
    ),
    add_completion=False,
    no_args_is_help=True,
)
emit_app = typer.Typer(help="Emit structured progress from inside the current Run.")
device_app = typer.Typer(help="Pair this machine and inspect its receiving connection.")
demo_app = typer.Typer(help="Send safe, built-in examples through the real delivery path.")
history_app = typer.Typer(help="Inspect and prune completed local Run history.")
completion_app = typer.Typer(help="Install or print deterministic shell completion.")
config_app = typer.Typer(
    help="Inspect or change local RunBuoy configuration.",
    invoke_without_command=True,
    no_args_is_help=False,
)
app.add_typer(device_app, name="device", rich_help_panel="Setup and diagnostics")
app.add_typer(config_app, name="config", rich_help_panel="Setup and diagnostics")
app.add_typer(history_app, name="history", rich_help_panel="Run management")
app.add_typer(demo_app, name="demo", rich_help_panel="Examples and automation")
app.add_typer(emit_app, name="emit", rich_help_panel="Examples and automation")
app.add_typer(completion_app, name="completion", rich_help_panel="Examples and automation")

console = Console()
error_console = Console(stderr=True)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"runbuoy {__version__}")
        raise typer.Exit()


@app.callback()
def root_options(
    version: bool = typer.Option(
        False,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Show the installed CLI version and exit.",
    ),
    no_color: bool = typer.Option(
        False,
        "--no-color",
        help="Disable styled terminal output. The NO_COLOR environment variable is also honored.",
    ),
) -> None:
    """RunBuoy sends a deliberately limited, read-only status projection to iPhone."""
    del version
    if no_color:
        console.no_color = True
        error_console.no_color = True


def _context() -> tuple[AppPaths, Config, CredentialStore, EventQueue]:
    paths = AppPaths.discover()
    paths.ensure()
    config = load_config(paths)
    return paths, config, CredentialStore(paths), EventQueue(paths.database)


def _json_print(value: Any, *, err: bool = False) -> None:
    typer.echo(json.dumps(value, sort_keys=True, default=str), err=err)


def _fail(
    message: str,
    *,
    code: str,
    json_output: bool = False,
    hint: str | None = None,
    exit_code: int = 1,
) -> NoReturn:
    if json_output:
        error: dict[str, Any] = {"code": code, "message": message}
        if hint:
            error["hint"] = hint
        _json_print({"ok": False, "error": error}, err=True)
    else:
        error_console.print(f"[red]Error:[/red] {message}")
        if hint:
            error_console.print(f"[dim]Next:[/dim] {hint}")
    raise typer.Exit(exit_code)


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _human_time(value: str | None) -> str:
    parsed = _parse_time(value)
    if parsed is None:
        return "—"
    return parsed.astimezone().strftime("%Y-%m-%d %H:%M:%S")


def _json_time(value: str | None) -> str | None:
    parsed = _parse_time(value)
    if parsed is None:
        return value
    return parsed.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _elapsed(item: dict[str, Any]) -> str:
    started = _parse_time(item.get("started_at"))
    if started is None:
        return "—"
    ended = _parse_time(item.get("ended_at")) or datetime.now(started.tzinfo)
    seconds = max(0, int((ended - started).total_seconds()))
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours:d}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"


def _progress_text(item: dict[str, Any]) -> str:
    progress = item.get("progress") or {}
    fraction = progress.get("fraction")
    if isinstance(fraction, int | float):
        return f"{max(0, min(100, round(float(fraction) * 100)))}%"
    return "—"


def _public_run(item: dict[str, Any]) -> dict[str, Any]:
    result = {
        key: item.get(key)
        for key in (
            "run_id",
            "title",
            "source",
            "status",
            "progress",
            "phase",
            "safe_message",
            "exit_code",
            "started_at",
            "updated_at",
            "ended_at",
        )
    }
    for key in ("started_at", "updated_at", "ended_at"):
        result[key] = _json_time(result.get(key))
    return result


def _completion_items(incomplete: str, *, active_only: bool) -> list[CompletionItem]:
    database = AppPaths.discover().database
    if not database.exists():
        return []
    escaped_incomplete = incomplete.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    clauses = ["run_id LIKE ? ESCAPE '\\'"]
    parameters: list[Any] = [f"{escaped_incomplete}%"]
    if active_only:
        placeholders = ",".join("?" for _ in TERMINAL_STATUSES)
        clauses.append(f"status NOT IN ({placeholders})")
        parameters.extend(sorted(TERMINAL_STATUSES))
    parameters.append(50)
    try:
        uri = database.resolve().as_uri() + "?mode=ro"
        with sqlite3.connect(uri, uri=True, timeout=0.05) as connection:
            rows = connection.execute(
                "SELECT run_id, title, status FROM runs WHERE "
                + " AND ".join(clauses)
                + " ORDER BY updated_at DESC LIMIT ?",
                parameters,
            ).fetchall()
    except (OSError, sqlite3.Error):
        return []
    return [CompletionItem(str(row[0]), help=f"{str(row[2]).lower()} · {row[1]}") for row in rows]


def _complete_any_run(incomplete: str) -> list[CompletionItem]:
    return _completion_items(incomplete, active_only=False)


def _complete_active_run(incomplete: str) -> list[CompletionItem]:
    return _completion_items(incomplete, active_only=True)


def _resolve_run(
    queue: EventQueue,
    reference: str,
    *,
    active_only: bool = False,
    json_output: bool = False,
) -> dict[str, Any]:
    if reference in {"@latest", "@active"}:
        matches = queue.list_runs(2, active_only=reference == "@active" or active_only)
        if not matches:
            _fail(
                "no matching local runs",
                code="run_not_found",
                json_output=json_output,
                hint="Start one with `runbuoy run -- COMMAND`.",
            )
        if reference == "@active" and len(matches) > 1:
            _fail(
                "more than one active run; provide an ID prefix",
                code="ambiguous_run",
                json_output=json_output,
                hint="Use `runbuoy list` to choose a Run.",
            )
        return matches[0]
    matches = queue.matching_runs(reference, active_only=active_only)
    exact = next((item for item in matches if item["run_id"] == reference), None)
    if exact is not None:
        return exact
    if not matches:
        _fail(
            f"unknown run: {reference}",
            code="run_not_found",
            json_output=json_output,
            hint="Use `runbuoy list -a` to see local Run IDs.",
        )
    if len(matches) > 1:
        choices = ", ".join(item["run_id"][:12] for item in matches[:5])
        _fail(
            f"run ID prefix is ambiguous: {reference} ({choices})",
            code="ambiguous_run",
            json_output=json_output,
            hint="Provide a longer ID prefix.",
        )
    return matches[0]


def _validate_run_options(
    command: list[str],
    progress_mode: ProgressMode,
    total: float | None,
    pattern: str | None,
) -> None:
    if not command:
        raise typer.BadParameter("a command is required after --")
    if progress_mode == ProgressMode.LINES and (total is None or total <= 0):
        raise typer.BadParameter("--total > 0 is required for lines progress")
    if progress_mode == ProgressMode.REGEX and not pattern:
        raise typer.BadParameter("--pattern is required for regex progress")
    if total is not None and total <= 0:
        raise typer.BadParameter("--total must be greater than zero")


@app.command(
    "run",
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
    rich_help_panel="Run management",
)
def run_command(
    command: list[str] = typer.Argument(
        ...,
        help=(
            "Command and arguments. Put them after `--` so their options are not parsed by RunBuoy."
        ),
    ),
    title: str | None = typer.Option(
        None,
        "--title",
        help="Safe title shown remotely. Paths and command arguments are not uploaded.",
    ),
    progress_mode: ProgressMode = typer.Option(
        ProgressMode.INDETERMINATE,
        "--progress",
        help="Progress source: structured, lines, regex, or indeterminate.",
    ),
    pattern: str | None = typer.Option(
        None,
        "--pattern",
        help="Regex with numeric current and total capture groups; required for regex progress.",
    ),
    total: float | None = typer.Option(
        None,
        "--total",
        help="Expected item count; required and greater than zero for lines progress.",
    ),
    match: str | None = typer.Option(
        None,
        "--match",
        help=(
            "Only matching terminal records advance lines progress. All records count when omitted."
        ),
    ),
    unit: str | None = typer.Option(None, "--unit", help="Short progress unit, such as files."),
    share_log_tail: int = typer.Option(
        0,
        "--share-log-tail",
        min=0,
        max=100,
        help="Upload an explicitly opted-in, redacted tail of up to 100 lines at completion.",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Write stable machine-readable JSON to stdout.",
    ),
    non_interactive: bool = typer.Option(
        False,
        "--non-interactive",
        help="Disable waiting prompts and terminal-only progress feedback.",
    ),
    wait: bool = typer.Option(
        False,
        "--wait",
        help="Wait for completion and return the target command's exit code.",
    ),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Suppress human startup output."),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Validate and preview local-only versus remotely visible fields without starting.",
    ),
    source: str = typer.Option("cli", "--source", hidden=True),
) -> None:
    """Start a durable local Run. The target argv and cwd remain on this machine."""
    _validate_run_options(command, progress_mode, total, pattern)
    safe_run_title = safe_title(command, title)
    if dry_run:
        preview = {
            "ok": True,
            "dry_run": True,
            "remote": {
                "title": safe_run_title,
                "source": source,
                "progress_mode": progress_mode.value,
                "shared_log_tail_lines": share_log_tail,
            },
            "local_only": {"argv": command, "cwd": os.getcwd()},
        }
        if json_output:
            _json_print(preview)
        else:
            console.print("[bold]Remote preview[/bold]")
            console.print(f"  title: {safe_run_title}")
            console.print(f"  progress: {progress_mode.value}")
            console.print(f"  shared log tail: {share_log_tail} lines")
            console.print("[bold]Local only[/bold]")
            console.print(f"  command: {shlex.join(command)}")
            console.print(f"  cwd: {os.getcwd()}")
        return

    paths, config, _credentials, queue = _context()
    config = ensure_machine_identity(paths, config)
    machine_id = config.machine_id
    if machine_id is None:  # pragma: no cover - guaranteed by ensure_machine_identity
        raise RuntimeError("machine identity initialization failed")
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
        title=safe_run_title,
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
        source=source,
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
        _fail(
            str(error),
            code="worker_start_failed",
            json_output=json_output,
            hint="Run `runbuoy doctor` to check tmux and local requirements.",
        )
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
    if json_output and not wait:
        _json_print(response)
    elif not json_output and not quiet:
        typer.echo(f"Run {run_id} started: {manifest.title}")
        typer.echo(f"  Status: runbuoy status {run_id[:12]}")
        typer.echo(f"  Logs:   runbuoy logs {run_id[:12]} -f")
        typer.echo(f"  Attach: runbuoy attach {run_id[:12]}")
        typer.echo(f"  Cancel: runbuoy cancel {run_id[:12]}")
    if not wait:
        return
    if not json_output and not quiet and not non_interactive:
        typer.echo("Waiting for the local result…")
    while not result_path.exists():
        time.sleep(0.1)
    result = json.loads(result_path.read_text(encoding="utf-8"))
    combined = {**response, "ok": result["exit_code"] == 0, "result": result}
    if json_output:
        _json_print(combined)
    elif not quiet:
        typer.echo(f"Run {result['status'].lower()} with exit code {result['exit_code']}.")
    raise typer.Exit(code=int(result["exit_code"]))


def _list_table(runs: list[dict[str, Any]]) -> Table:
    table = Table("ID", "Title", "Status", "Progress", "Started", "Elapsed")
    for item in runs:
        status = str(item["status"])
        style = {
            "RUNNING": "cyan",
            "STARTING": "cyan",
            "SUCCEEDED": "green",
            "FAILED": "red",
            "CANCELLED": "yellow",
            "LOST": "red",
        }.get(status)
        table.add_row(
            str(item["run_id"])[:12],
            str(item["title"]),
            f"[{style}]{status}[/{style}]" if style else status,
            _progress_text(item),
            _human_time(item.get("started_at") or item.get("updated_at")),
            _elapsed(item),
        )
    return table


@app.command("list", rich_help_panel="Run management")
def list_runs(
    all_runs: bool = typer.Option(
        False,
        "--all",
        "-a",
        help="Include completed history. The limit still applies.",
    ),
    status_filter: str | None = typer.Option(
        None,
        "--status",
        help="Filter by created, starting, running, succeeded, failed, cancelled, or lost.",
    ),
    json_output: bool = typer.Option(False, "--json", help="Write JSON to stdout."),
    limit: int = typer.Option(
        20,
        "--limit",
        "-n",
        min=1,
        max=200,
        help="Maximum number of rows to return.",
    ),
    watch: bool = typer.Option(False, "--watch", "-w", help="Refresh until interrupted."),
    interval: float = typer.Option(
        1.0,
        "--interval",
        min=0.2,
        max=60,
        help="Refresh interval in seconds when watching.",
    ),
) -> None:
    """List active local Runs by default; use --all to include history."""
    _paths, _config, _credentials, queue = _context()
    normalized_status: str | None = None
    if status_filter:
        normalized_status = status_filter.upper()
        if normalized_status not in {status.value for status in ExecutionStatus}:
            raise typer.BadParameter(f"unknown status: {status_filter}", param_hint="--status")
    while True:
        runs = queue.list_runs(
            limit,
            active_only=not all_runs and normalized_status is None,
            status=normalized_status,
        )
        if json_output:
            _json_print({"schema_version": 1, "runs": [_public_run(item) for item in runs]})
        elif runs:
            if watch and console.is_terminal:
                console.clear()
            console.print(_list_table(runs))
            if not all_runs and normalized_status is None:
                console.print("[dim]Showing active Runs. Use -a to include history.[/dim]")
        else:
            message = (
                "No active runs. Use `runbuoy list -a` to show history."
                if not all_runs and normalized_status is None
                else "No matching local runs."
            )
            typer.echo(message)
        if not watch:
            return
        time.sleep(interval)


def _print_status(item: dict[str, Any]) -> None:
    table = Table.grid(padding=(0, 2))
    rows = (
        ("Run ID", item["run_id"]),
        ("Title", item["title"]),
        ("Status", item["status"]),
        ("Progress", _progress_text(item)),
        ("Phase", item.get("phase") or "—"),
        ("Message", item.get("safe_message") or "—"),
        ("Started", _human_time(item.get("started_at"))),
        ("Updated", _human_time(item.get("updated_at"))),
        ("Elapsed", _elapsed(item)),
        ("Exit code", item.get("exit_code") if item.get("exit_code") is not None else "—"),
    )
    for label, value in rows:
        table.add_row(f"[bold]{label}[/bold]", str(value))
    console.print(table)


@app.command(rich_help_panel="Run management")
def status(
    run_id: str = typer.Argument(
        ...,
        help="Full Run ID, unique prefix, @latest, or @active.",
        autocompletion=_complete_any_run,
    ),
    json_output: bool = typer.Option(False, "--json", help="Write JSON to stdout."),
    watch: bool = typer.Option(False, "--watch", "-w", help="Follow changes until the Run ends."),
    interval: float = typer.Option(
        1.0,
        "--interval",
        min=0.2,
        max=60,
        help="Polling interval in seconds when watching.",
    ),
) -> None:
    """Show one local Run's state, progress, timing, and latest safe message."""
    _paths, _config, _credentials, queue = _context()
    item = _resolve_run(queue, run_id, json_output=json_output)
    last_updated: str | None = None
    while True:
        if item.get("updated_at") != last_updated:
            if json_output:
                _json_print({"schema_version": 1, "run": _public_run(item)})
            else:
                if watch and console.is_terminal:
                    console.clear()
                _print_status(item)
            last_updated = item.get("updated_at")
        if not watch or item["status"] in TERMINAL_STATUSES:
            return
        time.sleep(interval)
        refreshed = queue.get_run(str(item["run_id"]))
        if refreshed is None:
            _fail("local run disappeared", code="run_not_found", json_output=json_output)
        item = refreshed


@app.command(rich_help_panel="Run management")
def logs(
    run_id: str = typer.Argument(
        ...,
        help="Full Run ID, unique prefix, or @latest.",
        autocompletion=_complete_any_run,
    ),
    follow: bool = typer.Option(False, "--follow", "-f", help="Follow newly appended output."),
    lines: int = typer.Option(
        200,
        "--lines",
        "-n",
        min=1,
        max=10_000,
        help="Number of existing lines to show.",
    ),
) -> None:
    """Read the full local log. Full logs are not uploaded by this command."""
    _paths, _config, _credentials, queue = _context()
    item = _resolve_run(queue, run_id)
    path = Path(item["log_path"])
    if not path.exists():
        _fail(
            "log has not been created yet",
            code="log_not_ready",
            hint=f"Check startup with `runbuoy status {str(item['run_id'])[:12]}`.",
        )
    existing = path.read_text(encoding="utf-8", errors="replace").splitlines()[-lines:]
    typer.echo("\n".join(existing))
    if follow:
        raise typer.Exit(subprocess.call(["tail", "-n", "0", "-f", str(path)]))


@app.command(rich_help_panel="Run management")
def attach(
    run_id: str = typer.Argument(
        ...,
        help="Active Run ID, unique prefix, or @active.",
        autocompletion=_complete_active_run,
    ),
) -> None:
    """Attach this terminal to an active local tmux session."""
    _paths, _config, _credentials, queue = _context()
    item = _resolve_run(queue, run_id, active_only=True)
    session = item.get("tmux_session")
    if not session or not TmuxExecutor().exists(session):
        _fail(
            "local tmux session is no longer active",
            code="session_not_active",
            hint=f"Inspect the recorded result with `runbuoy status {str(item['run_id'])[:12]}`.",
        )
    raise typer.Exit(TmuxExecutor().attach(session))


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


@app.command(rich_help_panel="Run management")
def cancel(
    run_id: str = typer.Argument(
        ...,
        help="Active Run ID, unique prefix, or @active.",
        autocompletion=_complete_active_run,
    ),
    json_output: bool = typer.Option(False, "--json", help="Write JSON to stdout."),
) -> None:
    """Request cancellation through the active Run's local Unix socket."""
    _paths, _config, _credentials, queue = _context()
    item = _resolve_run(queue, run_id, active_only=True, json_output=json_output)
    manifest = RunManifest.model_validate_json(
        Path(item["manifest_path"]).read_text(encoding="utf-8")
    )
    try:
        response = _send_local(manifest.socket_path, manifest.socket_token, {"kind": "cancel"})
    except OSError:
        _fail(
            "local worker is not reachable",
            code="worker_unreachable",
            json_output=json_output,
            hint="Run `runbuoy doctor` and inspect the Run status.",
        )
    if not response.get("ok"):
        _fail(
            f"cancel rejected: {response.get('error')}",
            code="cancel_rejected",
            json_output=json_output,
        )
    if json_output:
        _json_print({"ok": True, "run_id": item["run_id"], "requested": "local_cancel"})
    else:
        typer.echo(f"Local cancellation requested for {item['run_id']}")


def _notification_payload(
    *,
    config: Config,
    title: str,
    body: str,
    subtitle: str | None,
    level: NotificationLevel,
    field: list[str] | None,
) -> dict[str, Any]:
    fields: list[dict[str, str]] = []
    for raw in field or []:
        if "=" not in raw:
            raise typer.BadParameter("--field must be label=value")
        label, value = raw.split("=", 1)
        safe_label = safe_message(label, 80) or ""
        if not safe_label:
            raise typer.BadParameter("--field label must not be empty")
        fields.append({"label": safe_label, "value": safe_message(value, 300) or ""})
    return {
        "title": safe_title(["notify"], title),
        "subtitle": safe_message(subtitle, 120),
        "body": safe_message(body, 2_000),
        "level": level.value,
        "fields": fields,
        "source": "cli",
        "machine_id": config.machine_id,
    }


def _notify(
    *,
    title: str,
    body: str,
    subtitle: str | None,
    level: NotificationLevel,
    field: list[str] | None,
    json_output: bool,
    dry_run: bool,
) -> None:
    _paths, config, credentials, _queue = _context()
    payload = _notification_payload(
        config=config,
        title=title,
        body=body,
        subtitle=subtitle,
        level=level,
        field=field,
    )
    if dry_run:
        if json_output:
            _json_print({"ok": True, "dry_run": True, "notification": payload})
        else:
            console.print("[bold]Notification preview[/bold]")
            console.print(f"  title: {payload['title']}")
            console.print(f"  body: {payload['body']}")
            console.print(f"  level: {payload['level']}")
            console.print("Nothing was sent.")
        return
    if credentials.get("machine_credential") is None:
        _fail(
            "this machine is not paired",
            code="not_paired",
            json_output=json_output,
            hint="Run `runbuoy device pair` and scan the code in the iOS app.",
        )
    client = RemoteClient(config, credentials)
    try:
        result = client.notify(payload)
    except (httpx.HTTPError, RemoteError, OSError) as error:
        _fail(
            safe_message(str(error)) or "notification request failed",
            code="notification_failed",
            json_output=json_output,
            hint="Run `runbuoy doctor` to check the server connection.",
        )
    finally:
        client.close()
    if json_output:
        _json_print({"ok": True, "accepted": True, "notification": result})
    else:
        notification_id = result.get("id") or result.get("notification_id")
        suffix = f" ({notification_id})" if notification_id else ""
        typer.echo(f"Notification accepted by the server{suffix}.")
        typer.echo("Open the iPhone app to confirm device delivery.")


@app.command(rich_help_panel="Run management")
def notify(
    title: str = typer.Option(..., "--title", help="Notification title."),
    body: str = typer.Option(..., "--body", help="Notification body."),
    subtitle: str | None = typer.Option(None, "--subtitle", help="Optional subtitle."),
    level: NotificationLevel = typer.Option(
        NotificationLevel.INFO,
        "--level",
        help="Notification severity.",
    ),
    field: list[str] | None = typer.Option(
        None,
        "--field",
        help="Repeat label=value to add compact structured fields.",
    ),
    json_output: bool = typer.Option(False, "--json", help="Write JSON to stdout."),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Preview the sanitized payload without sending it.",
    ),
) -> None:
    """Send a one-time notification without creating a managed Run."""
    _notify(
        title=title,
        body=body,
        subtitle=subtitle,
        level=level,
        field=field,
        json_output=json_output,
        dry_run=dry_run,
    )


def _pair(
    *,
    no_wait: bool,
    resume: bool,
    timeout: float,
    json_output: bool,
) -> None:
    if no_wait and resume:
        raise typer.BadParameter("--no-wait and --resume cannot be used together")
    paths, config, credentials, _queue = _context()
    config = ensure_machine_identity(paths, config)
    if resume:
        try:
            result = resume_pairing(config, credentials, timeout_seconds=timeout)
        except Exception as error:
            _fail(
                safe_message(str(error)) or "pairing failed",
                code="pairing_failed",
                json_output=json_output,
                hint="Start a fresh session with `runbuoy device pair` if it expired.",
            )
        safe_result = public_pairing_fields(result)
        if json_output:
            _json_print({"ok": True, "state": "paired", "pairing": safe_result})
        else:
            typer.echo("Machine paired.")
        return

    def show_created(created: dict[str, Any], qr_value: str) -> None:
        if json_output:
            payload: dict[str, Any] = {
                "ok": True,
                "state": "pending",
                "pairing": created,
                "qr": qr_value,
            }
            if no_wait:
                payload["resume"] = "runbuoy device pair --resume"
            _json_print(payload)
            return
        import qrcode

        qr = qrcode.QRCode(border=1)
        qr.add_data(qr_value)
        qr.print_ascii(invert=True)
        code = created.get("short_code") or created.get("challenge")
        typer.echo(f"Code: {code}")
        if no_wait:
            typer.echo("Pairing session saved. After scanning, run:")
            typer.echo("  runbuoy device pair --resume")
        else:
            typer.echo(f"Waiting up to {int(timeout)} seconds for the iOS app…")

    try:
        result, _qr_value = pair_machine(
            config,
            credentials,
            wait=not no_wait,
            timeout_seconds=timeout,
            on_created=show_created,
        )
    except Exception as error:
        _fail(
            safe_message(str(error)) or "pairing failed",
            code="pairing_failed",
            json_output=json_output,
            hint="Run `runbuoy doctor` and retry.",
        )
    machine_id = result.get("machine_id")
    if machine_id:
        config = config.model_copy(update={"machine_id": str(machine_id)})
        save_config(paths, config)
    safe_result = public_pairing_fields(result)
    if json_output and not no_wait:
        _json_print({"ok": True, "state": "paired", "pairing": safe_result})
    elif result.get("status") == "paired":
        typer.echo("Machine paired.")


@device_app.command("pair")
def device_pair(
    no_wait: bool = typer.Option(
        False,
        "--no-wait",
        help="Save the pending session and return; finish with --resume.",
    ),
    resume: bool = typer.Option(False, "--resume", help="Resume a saved pending session."),
    timeout: float = typer.Option(
        300,
        "--timeout",
        min=5,
        max=600,
        help="Seconds to wait for the iOS app.",
    ),
    json_output: bool = typer.Option(False, "--json", help="Write JSON/JSONL to stdout."),
) -> None:
    """Pair this machine with the RunBuoy iOS app."""
    _pair(no_wait=no_wait, resume=resume, timeout=timeout, json_output=json_output)


@device_app.command("status")
def device_status(
    check_server: bool = typer.Option(
        False,
        "--check-server",
        help="Also perform a bounded server health request.",
    ),
    json_output: bool = typer.Option(False, "--json", help="Write JSON to stdout."),
) -> None:
    """Show local identity, pairing state, and optional server reachability."""
    _paths, config, credentials, _queue = _context()
    result: dict[str, Any] = {
        "machine_id": config.machine_id,
        "machine_name": config.machine_name,
        "paired": credentials.get("machine_credential") is not None,
        "pairing_pending": credentials.get(PENDING_SESSION_KEY) is not None,
        "server_url": str(config.server_url),
    }
    if check_server:
        try:
            response = httpx.get(str(config.server_url).rstrip("/") + "/healthz", timeout=2)
            result["server_reachable"] = response.status_code == 200
        except Exception:
            result["server_reachable"] = False
    if json_output:
        _json_print({"ok": True, "device": result})
    else:
        for key, value in result.items():
            typer.echo(f"{key}: {value}")
        if not result["paired"]:
            typer.echo("Next: run `runbuoy device pair`.")


@app.command(rich_help_panel="Setup and diagnostics")
def doctor(
    json_output: bool = typer.Option(False, "--json", help="Write JSON to stdout."),
    strict: bool = typer.Option(
        False,
        "--strict",
        help="Exit non-zero unless local requirements, pairing, and server health all pass.",
    ),
    repair: bool = typer.Option(
        False,
        "--repair",
        help="Retry all locally queued delivery without changing Run execution state.",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Also show resolved local storage paths.",
    ),
) -> None:
    """Diagnose local requirements, pairing, server health, and pending delivery."""
    paths, config, credentials, queue = _context()
    checks: dict[str, Any] = {
        "cli_installed": True,
        "cli_version": __version__,
        "python_supported": sys.version_info >= (3, 12),
        "platform_supported": platform.system() in {"Darwin", "Linux"},
        "tmux_available": TmuxExecutor.available(),
        "paired": credentials.get("machine_credential") is not None,
        "server_reachable": False,
        "pending_events": queue.pending_event_count(),
        "pending_terminal_events": queue.pending_terminal_event_count(),
        "pending_machine_metadata": queue.pending_machine_metadata_count(),
        "last_delivery_error": safe_message(queue.latest_pending_delivery_error()),
    }
    try:
        response = httpx.get(str(config.server_url).rstrip("/") + "/healthz", timeout=2)
        checks["server_reachable"] = response.status_code == 200
    except Exception:
        pass
    repair_result = None
    if repair:
        client = RemoteClient(config, credentials)
        try:
            repair_result = repair_pending(queue, client, batch_size=config.batch_size)
        finally:
            client.close()
        checks["pending_events"] = repair_result.pending_events_after
        checks["pending_terminal_events"] = queue.pending_terminal_event_count()
        checks["pending_machine_metadata"] = repair_result.pending_machine_metadata_after
        checks["last_delivery_error"] = safe_message(queue.latest_pending_delivery_error())
        if repair_result.delivered_events > 0 or repair_result.repaired_machine_metadata > 0:
            checks["server_reachable"] = True
    required = ("python_supported", "platform_supported", "tmux_available")
    ok = all(bool(checks[key]) for key in required)
    ready = ok and bool(checks["paired"]) and bool(checks["server_reachable"])
    result: dict[str, Any] = {"ok": ok, "ready": ready, "checks": checks}
    if repair_result is not None:
        result["repair"] = repair_result.as_dict()
    if verbose:
        result["paths"] = {
            "config": str(paths.config),
            "data": str(paths.data),
            "state": str(paths.state),
            "cache": str(paths.cache),
        }
    if json_output:
        _json_print(result)
    else:
        rows = (
            ("CLI", True, __version__, None),
            (
                "Python ≥ 3.12",
                checks["python_supported"],
                platform.python_version(),
                "Upgrade Python.",
            ),
            ("Platform", checks["platform_supported"], platform.system(), None),
            (
                "tmux",
                checks["tmux_available"],
                "available" if checks["tmux_available"] else "missing",
                "Install tmux with your system package manager.",
            ),
            (
                "Paired",
                checks["paired"],
                str(checks["paired"]),
                "Run `runbuoy device pair`.",
            ),
            (
                "Server",
                checks["server_reachable"],
                str(config.server_url),
                "Check the URL and network connection.",
            ),
        )
        table = Table("Check", "Result", "Details", "Next step")
        for name, passed, details, hint in rows:
            symbol = "[green]✓[/green]" if passed else "[yellow]![/yellow]"
            table.add_row(name, symbol, str(details), "" if passed or not hint else hint)
        console.print(table)
        typer.echo(f"Pending local events: {checks['pending_events']}")
        typer.echo(f"Pending terminal events: {checks['pending_terminal_events']}")
        typer.echo(f"Pending Machine metadata: {checks['pending_machine_metadata']}")
        if checks["last_delivery_error"] is not None:
            typer.echo(f"Last delivery error: {checks['last_delivery_error']}")
        if repair_result is not None:
            typer.echo(
                f"Repair delivered {repair_result.delivered_events} event(s) and "
                f"{repair_result.repaired_machine_metadata} Machine update(s)."
            )
            typer.echo(
                "Repair complete."
                if repair_result.completed
                else "Repair incomplete; queued delivery remains unchanged locally."
            )
        elif checks["pending_terminal_events"] or checks["pending_machine_metadata"]:
            typer.echo("Recovery: run `runbuoy doctor --repair`.")
        typer.echo(
            "Ready for delivery." if ready else "Local CLI works, but delivery setup is incomplete."
        )
        if verbose:
            for key, value in result["paths"].items():
                typer.echo(f"{key}_path: {value}")
    if repair_result is not None and not repair_result.completed:
        raise typer.Exit(1)
    if strict and not ready:
        raise typer.Exit(1)
    if not strict and not ok:
        raise typer.Exit(1)


@app.command(rich_help_panel="Examples and automation")
def capabilities(
    json_output: bool = typer.Option(False, "--json", help="Write JSON to stdout."),
) -> None:
    """Describe stable CLI capabilities for scripts and agent integrations."""
    progress_modes = [mode.value for mode in ProgressMode]
    result = {
        "schema_version": 1,
        "cli_version": __version__,
        "platforms": ["macos", "linux"],
        "progress_modes": progress_modes,
        "local_commands": ["list", "status", "logs", "attach", "cancel"],
        "demo_commands": ["notification", "live-activity"],
        "shell_completion": ["bash", "zsh", "fish", "powershell", "pwsh"],
        "remote_control": False,
        "inbound_tcp": False,
        "full_logs_uploaded_by_default": False,
    }
    if json_output:
        _json_print(result)
    else:
        typer.echo("Progress: " + ", ".join(progress_modes))
        typer.echo("Shell completion: run `runbuoy completion install SHELL`")
        typer.echo("Remote control: disabled")


@completion_app.command("show")
def completion_show(
    shell: CompletionShell = typer.Argument(..., help="Shell script format to print."),
) -> None:
    """Print a completion script without changing shell configuration."""
    typer.echo(
        get_completion_script(
            prog_name="runbuoy",
            complete_var="_RUNBUOY_COMPLETE",
            shell=shell.value,
        )
    )


@completion_app.command("install")
def completion_install(
    shell: CompletionShell = typer.Argument(..., help="Shell configuration to update."),
) -> None:
    """Install completion for an explicitly selected shell."""
    installed_shell, path = install_completion(
        shell=shell.value,
        prog_name="runbuoy",
        complete_var="_RUNBUOY_COMPLETE",
    )
    typer.echo(f"{installed_shell} completion installed in {path}")
    typer.echo("Restart the terminal for completion to take effect.")


def _config_result(config: Config) -> dict[str, Any]:
    return {
        "server_url": str(config.server_url),
        "machine_id": config.machine_id,
        "machine_name": config.machine_name,
        "upload_interval_seconds": config.upload_interval_seconds,
        "batch_size": config.batch_size,
        "request_timeout_seconds": config.request_timeout_seconds,
        "terminal_retry_window_seconds": config.terminal_retry_window_seconds,
        "credential_storage": "keyring-or-mode-0600-fallback",
    }


def _update_config(
    *,
    server_url: str | None,
    machine_name: str | None,
) -> tuple[AppPaths, Config]:
    paths, config, _credentials, _queue = _context()
    updates: dict[str, Any] = {}
    if server_url is not None:
        updates["server_url"] = server_url
    if machine_name is not None:
        cleaned = (safe_message(machine_name, 120) or "").strip()
        if not cleaned:
            raise typer.BadParameter("--machine-name must not be empty")
        updates["machine_name"] = cleaned
    if updates:
        try:
            config = Config.model_validate({**config.model_dump(), **updates})
        except ValidationError as error:
            raise typer.BadParameter(str(error)) from error
        save_config(paths, config)
    return paths, config


def _show_config(config: Config, *, json_output: bool) -> None:
    result = _config_result(config)
    if json_output:
        _json_print(result)
    else:
        for key, value in result.items():
            typer.echo(f"{key}: {value}")


@config_app.callback()
def config_command(
    ctx: typer.Context,
    json_output: bool = typer.Option(False, "--json", help="Write JSON to stdout."),
) -> None:
    """Show configuration when no config subcommand is given."""
    if ctx.invoked_subcommand is not None:
        return
    _paths, config = _update_config(server_url=None, machine_name=None)
    _show_config(config, json_output=json_output)


@config_app.command("show")
def config_show(
    json_output: bool = typer.Option(False, "--json", help="Write JSON to stdout."),
) -> None:
    """Show effective non-secret configuration."""
    _paths, config = _update_config(server_url=None, machine_name=None)
    _show_config(config, json_output=json_output)


@config_app.command("set")
def config_set(
    server_url: str | None = typer.Option(None, "--server-url", help="RunBuoy server base URL."),
    machine_name: str | None = typer.Option(
        None,
        "--machine-name",
        help="Safe machine display name.",
    ),
    json_output: bool = typer.Option(False, "--json", help="Write JSON to stdout."),
) -> None:
    """Change one or more non-secret settings and show the result."""
    if server_url is None and machine_name is None:
        raise typer.BadParameter("provide --server-url and/or --machine-name")
    paths, config = _update_config(server_url=server_url, machine_name=machine_name)
    if machine_name is not None and config.machine_id is not None:
        credentials = CredentialStore(paths)
        if credentials.get("machine_credential") is not None:
            queue = EventQueue(paths.database)
            queue.queue_machine_metadata(config.machine_id, config.machine_name)
            client = RemoteClient(config, credentials)
            try:
                client.update_machine(config.machine_id, config.machine_name)
            except (httpx.HTTPError, RemoteError, OSError) as error:
                queue.mark_machine_metadata_failed(
                    config.machine_id,
                    config.machine_name,
                    str(error),
                    1,
                )
                _fail(
                    "Machine name saved locally; server sync is queued.",
                    code="machine_name_sync_pending",
                    json_output=json_output,
                    hint="Repeat this command or start a Run after the connection recovers.",
                )
            finally:
                client.close()
            queue.mark_machine_metadata_delivered(config.machine_id, config.machine_name)
    _show_config(config, json_output=json_output)


@config_app.command("path")
def config_path(
    json_output: bool = typer.Option(False, "--json", help="Write JSON to stdout."),
) -> None:
    """Show resolved config, data, state, and cache locations."""
    paths = AppPaths.discover()
    result = {
        "config_file": str(paths.config_file),
        "database": str(paths.database),
        "config_dir": str(paths.config),
        "data_dir": str(paths.data),
        "state_dir": str(paths.state),
        "cache_dir": str(paths.cache),
    }
    if json_output:
        _json_print(result)
    else:
        for key, value in result.items():
            typer.echo(f"{key}: {value}")


def _retention_delta(value: str) -> timedelta:
    match = re.fullmatch(r"([1-9][0-9]*)([mhdw])", value.strip().lower())
    if match is None:
        raise typer.BadParameter(
            "use a positive duration such as 90m, 24h, 30d, or 8w",
            param_hint="--older-than",
        )
    amount = int(match.group(1))
    unit = match.group(2)
    seconds = amount * {"m": 60, "h": 3600, "d": 86_400, "w": 604_800}[unit]
    return timedelta(seconds=seconds)


@history_app.command("prune")
def history_prune(
    older_than: str = typer.Option(
        "30d",
        "--older-than",
        help="Remove terminal Runs older than this duration, for example 24h, 30d, or 8w.",
    ),
    limit: int = typer.Option(
        1000,
        "--limit",
        min=1,
        max=10_000,
        help="Maximum number of Runs to remove in one invocation.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="List matching Runs without deleting database rows or local files.",
    ),
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Skip the interactive confirmation.",
    ),
    include_unsynced: bool = typer.Option(
        False,
        "--include-unsynced",
        help="Also discard Runs whose local events have not been delivered.",
    ),
    json_output: bool = typer.Option(False, "--json", help="Write JSON to stdout."),
) -> None:
    """Permanently remove old terminal Run records and their local files."""
    paths, _config, _credentials, queue = _context()
    cutoff = datetime.now(UTC) - _retention_delta(older_than)
    candidates = queue.terminal_runs_before(
        cutoff,
        include_unsynced=include_unsynced,
        limit=limit,
    )
    summary = {
        "matched": len(candidates),
        "cutoff": cutoff.isoformat(timespec="seconds").replace("+00:00", "Z"),
        "include_unsynced": include_unsynced,
        "run_ids": [item["run_id"] for item in candidates],
    }
    if dry_run or not candidates:
        if json_output:
            _json_print({"ok": True, "dry_run": dry_run, **summary})
        else:
            typer.echo(
                f"{len(candidates)} terminal Runs match --older-than {older_than}. "
                + ("Nothing was deleted." if dry_run else "Nothing to remove.")
            )
            for item in candidates:
                typer.echo(f"  {str(item['run_id'])[:12]}  {item['title']}")
        return
    if not yes and not typer.confirm(
        f"Permanently remove {len(candidates)} local Run records and their files?"
    ):
        raise typer.Abort()
    runs_root = (paths.state / "runs").resolve()
    removed_ids: list[str] = []
    failed: list[dict[str, str]] = []
    for item in candidates:
        run_id = str(item["run_id"])
        run_dir = Path(str(item["manifest_path"])).resolve().parent
        try:
            run_dir.relative_to(runs_root)
        except ValueError:
            failed.append({"run_id": run_id, "error": "run directory is outside state root"})
            continue
        try:
            if run_dir.exists():
                shutil.rmtree(run_dir)
        except OSError as error:
            failed.append({"run_id": run_id, "error": safe_message(str(error)) or "delete failed"})
            continue
        removed_ids.append(run_id)
    queue.delete_runs(removed_ids)
    result = {
        "ok": not failed,
        "removed": len(removed_ids),
        "recoverable": False,
        "failed": failed,
        **summary,
    }
    if json_output:
        _json_print(result)
    else:
        typer.echo(
            f"Removed {len(removed_ids)} local Run records and file directories permanently."
        )
        if failed:
            error_console.print(f"[yellow]{len(failed)} Runs could not be removed.[/yellow]")
    if failed:
        raise typer.Exit(1)


@demo_app.command("notification")
def demo_notification(
    json_output: bool = typer.Option(False, "--json", help="Write JSON to stdout."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview without sending."),
) -> None:
    """Send a ready-made notification through the configured server."""
    _notify(
        title="RunBuoy test notification",
        body="Delivery is configured. This notification was sent by the built-in CLI demo.",
        subtitle="Safe delivery check",
        level=NotificationLevel.SUCCESS,
        field=["Source=runbuoy demo notification"],
        json_output=json_output,
        dry_run=dry_run,
    )


def _require_delivery_ready(*, json_output: bool) -> None:
    _paths, config, credentials, _queue = _context()
    if credentials.get("machine_credential") is None:
        _fail(
            "this machine is not paired",
            code="not_paired",
            json_output=json_output,
            hint="Run `runbuoy device pair` before testing delivery.",
        )
    try:
        response = httpx.get(str(config.server_url).rstrip("/") + "/healthz", timeout=2)
    except Exception:
        response = None
    if response is None or response.status_code != 200:
        _fail(
            "the configured RunBuoy server is not reachable",
            code="server_unreachable",
            json_output=json_output,
            hint="Run `runbuoy doctor` and verify `runbuoy config show`.",
        )


@demo_app.command("live-activity")
def demo_live_activity(
    duration: float = typer.Option(
        15,
        "--duration",
        min=8,
        max=300,
        help="Approximate demo duration in seconds; at least 8 allows the start policy to trigger.",
    ),
    result: DemoResult = typer.Option(
        DemoResult.SUCCESS,
        "--result",
        help="Finish the demo successfully or with a failure.",
    ),
    attention: bool = typer.Option(
        False,
        "--attention",
        help="Emit an action-required state during the demo.",
    ),
    wait: bool = typer.Option(
        False,
        "--wait",
        help="Wait locally and return the demo process exit code.",
    ),
    json_output: bool = typer.Option(False, "--json", help="Write JSON to stdout."),
) -> None:
    """Create a real managed Run with phases and progress for Live Activity validation."""
    _require_delivery_ready(json_output=json_output)
    steps = [
        (5, "Preparing", "Preparing the Live Activity demo"),
        (30, "Downloading", "Downloading safe example data"),
        (65, "Processing", "Processing the example"),
        (100, "Finishing", "Finalizing the demo"),
    ]
    script_lines = [
        "import time",
        "from runbuoy import attention, progress",
        f"steps = {steps!r}",
        f"delay = {duration!r} / len(steps)",
        "for index, (current, phase, message) in enumerate(steps):",
        "    progress(current, 100, unit='percent', phase=phase, message=message)",
    ]
    if attention:
        script_lines.extend(
            [
                "    if index == 2:",
                "        attention('Demo attention requested')",
            ]
        )
    script_lines.extend(
        [
            "    time.sleep(delay)",
            f"raise SystemExit({1 if result == DemoResult.FAILURE else 0})",
        ]
    )
    run_command(
        command=[sys.executable, "-c", "\n".join(script_lines)],
        title=f"RunBuoy Live Activity demo ({result.value})",
        progress_mode=ProgressMode.STRUCTURED,
        pattern=None,
        total=None,
        match=None,
        unit=None,
        share_log_tail=0,
        json_output=json_output,
        non_interactive=False,
        wait=wait,
        quiet=False,
        dry_run=False,
        source="demo",
    )


@emit_app.command("progress")
def emit_progress(
    current: float = typer.Option(..., "--current", help="Completed amount."),
    total: float = typer.Option(..., "--total", help="Positive total amount."),
    unit: str | None = typer.Option(None, "--unit", help="Short unit label."),
    phase: str | None = typer.Option(None, "--phase", help="Current safe phase."),
    message: str | None = typer.Option(None, "--message", help="Current safe message."),
) -> None:
    """Emit explicit determinate progress from inside a structured Run."""
    sdk.progress(current, total, unit=unit, phase=phase, message=message)


@emit_app.command("phase")
def emit_phase(value: str = typer.Argument(..., help="New safe phase.")) -> None:
    """Change the current Run phase."""
    sdk.phase(value)


@emit_app.command("message")
def emit_message(value: str = typer.Argument(..., help="New safe status message.")) -> None:
    """Change the current Run message."""
    sdk.message(value)


@emit_app.command("attention")
def emit_attention(
    value: str = typer.Argument(..., help="Safe attention message."),
    status: AttentionStatus = typer.Option(
        AttentionStatus.ACTION_REQUIRED,
        "--status",
        help="Attention severity.",
    ),
) -> None:
    """Mark the current Run as needing information, warning, or action."""
    sdk.attention(value, status=status.value)


@app.command("_worker", hidden=True)
def worker_command(
    manifest: Path = typer.Option(..., "--manifest", exists=True, dir_okay=False),
) -> None:
    raise typer.Exit(run_worker(manifest))


def main() -> None:
    app()
