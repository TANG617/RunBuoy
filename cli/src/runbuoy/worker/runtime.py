from __future__ import annotations

import errno
import json
import os
import pty
import selectors
import signal
import subprocess
import sys
import threading
import time
from collections import deque
from contextlib import suppress
from pathlib import Path
from typing import Any

from runbuoy.config import CredentialStore, load_config
from runbuoy.models import ExecutionStatus, Progress, RunManifest, WorkerResult, utc_now
from runbuoy.networking.client import RemoteClient, drain_pending, outbox_lease
from runbuoy.paths import AppPaths
from runbuoy.persistence.store import EventQueue
from runbuoy.progress_adapters import ProgressAdapter, make_adapter
from runbuoy.security.redaction import safe_message
from runbuoy.worker.signals import escalate_process_group
from runbuoy.worker.socket_server import EventSocketServer


def _safe_log_tail(path: Path, lines: int) -> list[str]:
    if lines <= 0 or not path.exists():
        return []
    tail: deque[str] = deque(maxlen=min(lines, 100))
    with path.open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            cleaned = safe_message(line.rstrip("\r\n"))
            if cleaned:
                tail.append(cleaned)
    result: list[str] = []
    total_bytes = 0
    for line in tail:
        encoded = line[:500].encode("utf-8")
        if total_bytes + len(encoded) > 16_000:
            break
        result.append(line[:500])
        total_bytes += len(encoded)
    return result


class Worker:
    immediate_upload_events = frozenset(
        {
            "run.starting",
            "run.started",
            "run.phase_changed",
            "run.attention_required",
            "run.succeeded",
            "run.failed",
            "run.cancelled",
            "run.lost",
        }
    )

    def __init__(self, manifest: RunManifest, paths: AppPaths) -> None:
        self.manifest = manifest
        self.paths = paths
        self.queue = EventQueue(paths.database)
        self.cancel_requested = threading.Event()
        self.upload_wakeup = threading.Event()
        self.upload_stop = threading.Event()
        self._event_lock = threading.Lock()
        self._process: subprocess.Popen[bytes] | None = None
        self._last_explicit_current = -1.0
        self._socket_server: EventSocketServer | None = None
        self._handoff_ack = threading.Event()
        self._adapter: ProgressAdapter | None = None

    def emit(self, event_type: str, payload: dict[str, Any]) -> None:
        with self._event_lock:
            self.queue.append_event(self.manifest.run_id, event_type, payload)
        if event_type in self.immediate_upload_events:
            self.upload_wakeup.set()

    def on_progress(self, progress: Progress) -> None:
        payload: dict[str, Any] = {"progress": progress.model_dump(exclude_none=True)}
        if progress.phase is not None:
            payload["phase"] = progress.phase
        if progress.message is not None:
            payload["message"] = progress.message
        self.emit("run.progress", payload)

    def socket_handler(self, request: dict[str, Any]) -> dict[str, Any]:
        kind = str(request.get("kind", ""))
        try:
            if kind == "handoff_ack":
                if str(request.get("nonce", "")) != self.manifest.handoff_nonce:
                    return {"ok": False, "error": "handoff_nonce_mismatch"}
                self._handoff_ack.set()
                return {"ok": True, "state": "acknowledged"}
            if kind == "cancel":
                self.cancel_requested.set()
                return {"ok": True}
            if kind == "progress":
                current = float(request["current"])
                total = float(request["total"])
                if current < self._last_explicit_current:
                    return {"ok": False, "error": "stale_progress"}
                progress = Progress.determinate(
                    current,
                    total,
                    source="explicit",
                    unit=request.get("unit"),
                    phase=safe_message(request.get("phase"), 120),
                    message=safe_message(request.get("message")),
                )
                self._last_explicit_current = progress.current or 0
                self.on_progress(progress)
            elif kind == "phase":
                phase = safe_message(str(request["phase"]), 120)
                self.emit("run.phase_changed", {"phase": phase})
            elif kind == "message":
                message = safe_message(str(request["message"]))
                self.emit("run.message", {"message": message})
            elif kind == "attention":
                status = str(request.get("attention_status", "ACTION_REQUIRED"))
                if status not in {"INFORMATION", "WARNING", "ACTION_REQUIRED"}:
                    return {"ok": False, "error": "invalid_attention_status"}
                self.emit(
                    "run.attention_required",
                    {
                        "attention_status": status,
                        "message": safe_message(str(request.get("message", ""))),
                    },
                )
            else:
                return {"ok": False, "error": "unknown_event_kind"}
        except (KeyError, TypeError, ValueError):
            return {"ok": False, "error": "invalid_event"}
        return {"ok": True}

    def _upload_loop(self) -> None:
        config = load_config(self.paths)
        credentials = CredentialStore(self.paths)
        try:
            credential = credentials.get("machine_credential")
        except Exception:
            return
        if credential is None:
            return
        try:
            client = RemoteClient(config, credentials)
        except Exception:
            return
        try:
            while not self.upload_stop.is_set():
                with outbox_lease(self.paths.outbox_lease) as acquired:
                    if acquired:
                        with suppress(Exception):
                            drain_pending(
                                self.queue,
                                client,
                                batch_size=config.batch_size,
                            )
                self.upload_wakeup.wait(config.upload_interval_seconds)
                self.upload_wakeup.clear()
            with outbox_lease(self.paths.outbox_lease) as acquired:
                if acquired:
                    with suppress(Exception):
                        drain_pending(
                            self.queue,
                            client,
                            batch_size=config.batch_size,
                        )
        finally:
            client.close()

    def _write_handoff(self, state: str) -> None:
        path = Path(self.manifest.handoff_path)
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "state": state,
                    "nonce": self.manifest.handoff_nonce,
                    "socket_path": self.manifest.socket_path,
                    "worker_pid": os.getpid(),
                }
            ),
            encoding="utf-8",
        )
        temporary.chmod(0o600)
        os.replace(temporary, path)

    def _wait_for_handoff(self) -> None:
        deadline = time.monotonic() + self.manifest.handoff_timeout_seconds
        while not self._handoff_ack.wait(0.05):
            if self.cancel_requested.is_set():
                raise RuntimeError("worker stopped before handoff acknowledgement")
            run = self.queue.get_run(self.manifest.run_id)
            if run is None or run["status"] == ExecutionStatus.LOST.value:
                raise RuntimeError("CLI abandoned the Run before handoff acknowledgement")
            if time.monotonic() >= deadline:
                raise TimeoutError("CLI did not acknowledge the ready Worker")
        self._write_handoff("acknowledged")

    def _request_cancel(self) -> None:
        process = self._process
        if process is None:
            return
        escalate_process_group(
            process.pid,
            grace_seconds=self.manifest.cancel_grace_seconds,
            is_alive=lambda: process.poll() is None,
        )

    def run(self) -> int:
        log_path = Path(self.manifest.log_path)
        result_path = Path(self.manifest.result_path)
        socket_path = Path(self.manifest.socket_path)
        socket_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        upload_thread = threading.Thread(
            target=self._upload_loop,
            name="runbuoy-uploader",
            daemon=True,
        )
        upload_thread.start()
        self._socket_server = EventSocketServer(
            socket_path, self.manifest.socket_token, self.socket_handler
        )
        old_handlers: dict[signal.Signals, Any] = {}

        def request_cancel(_signum: int, _frame: Any) -> None:
            self.cancel_requested.set()

        for handled_signal in (signal.SIGINT, signal.SIGTERM):
            old_handlers[handled_signal] = signal.signal(handled_signal, request_cancel)
        try:
            self._socket_server.start()
            self.emit("run.starting", {"message": "Preparing local process"})
            self._adapter = make_adapter(self.manifest, self.on_progress)
            self._write_handoff("ready")
            self._wait_for_handoff()
            return self._run_target(utc_now(), log_path, result_path)
        except Exception as error:
            before_handoff = not self._handoff_ack.is_set()
            message = safe_message(
                "Worker handoff failed"
                if before_handoff
                else f"Worker failed: {type(error).__name__}"
            )
            status = ExecutionStatus.LOST if before_handoff else ExecutionStatus.FAILED
            event_type = "run.lost" if before_handoff else "run.failed"
            reason = "handoff_failed" if before_handoff else "worker_error"
            exit_code = 125 if before_handoff else 127
            with suppress(ValueError):
                self.emit(
                    event_type,
                    {
                        "exit_code": exit_code,
                        "termination_reason": reason,
                        "message": message,
                    },
                )
            result = WorkerResult(
                run_id=self.manifest.run_id,
                status=status,
                exit_code=exit_code,
                started_at=None,
                ended_at=utc_now(),
                termination_reason=reason,
            )
            self._write_result(result_path, result)
            return exit_code
        finally:
            if self._socket_server is not None:
                self._socket_server.close()
            self.upload_stop.set()
            self.upload_wakeup.set()
            upload_thread.join(timeout=6)
            for handled_signal, previous in old_handlers.items():
                signal.signal(handled_signal, previous)

    def _run_target(self, started_at: Any, log_path: Path, result_path: Path) -> int:
        adapter = self._adapter
        if adapter is None:  # pragma: no cover - protected by the handoff lifecycle
            raise RuntimeError("progress adapter was not initialized")
        master_fd, slave_fd = pty.openpty()
        environment = os.environ.copy()
        environment.update(
            {
                "RUNBUOY_RUN_ID": self.manifest.run_id,
                "RUNBUOY_EVENT_SOCKET": self.manifest.socket_path,
                "RUNBUOY_EVENT_TOKEN": self.manifest.socket_token,
            }
        )
        try:
            try:
                process = subprocess.Popen(
                    self.manifest.argv,
                    cwd=self.manifest.cwd,
                    env=environment,
                    stdin=slave_fd,
                    stdout=slave_fd,
                    stderr=slave_fd,
                    start_new_session=True,
                )
            except Exception:
                os.close(master_fd)
                raise
        finally:
            os.close(slave_fd)
        self._process = process
        self.queue.update_runtime(
            self.manifest.run_id,
            worker_pid=os.getpid(),
            process_group=process.pid,
        )
        try:
            self.emit("run.started", {"message": "Run started"})
        except Exception:
            self.cancel_requested.set()
            self._request_cancel()
            process.wait()
            raise
        os.set_blocking(master_fd, False)
        selector = selectors.DefaultSelector()
        selector.register(master_fd, selectors.EVENT_READ)
        cancel_thread: threading.Thread | None = None
        last_heartbeat = time.monotonic()
        drained_after_exit = 0
        log_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        with log_path.open("ab", buffering=0) as log:
            log_path.chmod(0o600)
            while True:
                if self.cancel_requested.is_set() and cancel_thread is None:
                    cancel_thread = threading.Thread(
                        target=self._request_cancel, name="runbuoy-cancel", daemon=True
                    )
                    cancel_thread.start()
                events = selector.select(0.1)
                had_output = False
                for _key, _mask in events:
                    try:
                        chunk = os.read(master_fd, 65_536)
                    except OSError as error:
                        if error.errno == errno.EIO:
                            chunk = b""
                        else:
                            raise
                    if chunk:
                        had_output = True
                        log.write(chunk)
                        with suppress(OSError):
                            os.write(sys.stdout.fileno(), chunk)
                        adapter.feed(chunk)
                if time.monotonic() - last_heartbeat >= 15:
                    self.emit("run.heartbeat", {})
                    last_heartbeat = time.monotonic()
                if process.poll() is not None:
                    drained_after_exit = 0 if had_output else drained_after_exit + 1
                    if drained_after_exit >= 2:
                        break
        selector.close()
        os.close(master_fd)
        adapter.close()
        if cancel_thread is not None:
            cancel_thread.join(timeout=self.manifest.cancel_grace_seconds * 2 + 1)
        raw_exit_code = process.wait()
        cancelled = self.cancel_requested.is_set()
        exit_code = 130 if cancelled and raw_exit_code < 0 else raw_exit_code
        ended_at = utc_now()
        payload: dict[str, Any] = {"exit_code": exit_code}
        log_tail = _safe_log_tail(log_path, self.manifest.share_log_tail)
        if log_tail:
            payload["safe_log_tail"] = log_tail
        if cancelled:
            status = ExecutionStatus.CANCELLED
            payload["termination_reason"] = "local_cancel"
            payload["message"] = "Run cancelled locally"
            event_type = "run.cancelled"
        elif raw_exit_code == 0:
            status = ExecutionStatus.SUCCEEDED
            payload["message"] = "Run completed"
            event_type = "run.succeeded"
        else:
            status = ExecutionStatus.FAILED
            payload["message"] = "Run failed"
            event_type = "run.failed"
        self.emit(event_type, payload)
        result = WorkerResult(
            run_id=self.manifest.run_id,
            status=status,
            exit_code=exit_code,
            started_at=started_at,
            ended_at=ended_at,
            termination_reason="local_cancel" if cancelled else None,
        )
        self._write_result(result_path, result)
        return exit_code

    @staticmethod
    def _write_result(path: Path, result: WorkerResult) -> None:
        temporary = path.with_suffix(".tmp")
        temporary.write_text(result.model_dump_json(indent=2), encoding="utf-8")
        temporary.chmod(0o600)
        os.replace(temporary, path)


def run_worker(manifest_path: Path) -> int:
    if manifest_path.stat().st_mode & 0o077:
        raise PermissionError("manifest must only be readable by its owner")
    manifest = RunManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    paths = AppPaths.discover()
    paths.ensure()
    return Worker(manifest, paths).run()
