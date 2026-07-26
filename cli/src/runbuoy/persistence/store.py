from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

from runbuoy.ids import uuid7
from runbuoy.models import ExecutionStatus, RunEvent, utc_now
from runbuoy.security.redaction import assert_safe_remote_payload

TERMINAL_STATUSES = {
    ExecutionStatus.SUCCEEDED.value,
    ExecutionStatus.FAILED.value,
    ExecutionStatus.CANCELLED.value,
    ExecutionStatus.LOST.value,
}
EVENT_STATUS = {
    "run.created": ExecutionStatus.CREATED.value,
    "run.starting": ExecutionStatus.STARTING.value,
    "run.started": ExecutionStatus.RUNNING.value,
    "run.succeeded": ExecutionStatus.SUCCEEDED.value,
    "run.failed": ExecutionStatus.FAILED.value,
    "run.cancelled": ExecutionStatus.CANCELLED.value,
    "run.lost": ExecutionStatus.LOST.value,
}


class EventQueue:
    def __init__(self, database: Path) -> None:
        self.database = database
        database.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        self._initialize()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database, timeout=10, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 10000")
        return connection

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        connection = self.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(
                """
                PRAGMA journal_mode = WAL;
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    machine_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    source TEXT NOT NULL DEFAULT 'cli',
                    status TEXT NOT NULL,
                    progress_json TEXT,
                    phase TEXT,
                    safe_message TEXT,
                    exit_code INTEGER,
                    started_at TEXT,
                    updated_at TEXT NOT NULL,
                    ended_at TEXT,
                    manifest_path TEXT NOT NULL,
                    log_path TEXT NOT NULL,
                    result_path TEXT NOT NULL,
                    socket_path TEXT NOT NULL,
                    tmux_session TEXT,
                    worker_pid INTEGER,
                    process_group INTEGER,
                    remote_initialized INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS events (
                    event_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL REFERENCES runs(run_id),
                    seq INTEGER NOT NULL,
                    event_type TEXT NOT NULL,
                    event_json TEXT NOT NULL,
                    delivered INTEGER NOT NULL DEFAULT 0,
                    attempt_count INTEGER NOT NULL DEFAULT 0,
                    next_attempt_at REAL NOT NULL DEFAULT 0,
                    last_error TEXT,
                    created_at TEXT NOT NULL,
                    UNIQUE(run_id, seq)
                );
                CREATE INDEX IF NOT EXISTS idx_events_delivery
                    ON events(delivered, next_attempt_at, run_id, seq);
                """
            )
            columns = {
                row["name"] for row in connection.execute("PRAGMA table_info(runs)").fetchall()
            }
            if "remote_initialized" not in columns:
                connection.execute(
                    "ALTER TABLE runs ADD COLUMN remote_initialized INTEGER NOT NULL DEFAULT 0"
                )

    def create_run(
        self,
        *,
        run_id: str,
        machine_id: str,
        title: str,
        manifest_path: str,
        log_path: str,
        result_path: str,
        socket_path: str,
        tmux_session: str | None,
    ) -> RunEvent:
        now = utc_now()
        with self.transaction() as connection:
            connection.execute(
                """
                INSERT INTO runs(
                    run_id, machine_id, title, status, updated_at, manifest_path,
                    log_path, result_path, socket_path, tmux_session
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    machine_id,
                    title,
                    ExecutionStatus.CREATED.value,
                    now.isoformat(),
                    manifest_path,
                    log_path,
                    result_path,
                    socket_path,
                    tmux_session,
                ),
            )
            return self._append_event_in_transaction(
                connection,
                run_id,
                "run.created",
                {
                    "title": title,
                    "source": "cli",
                    "health_status": "HEALTHY",
                    "attention_status": "NONE",
                },
                now,
            )

    def append_event(
        self,
        run_id: str,
        event_type: str,
        payload: dict[str, Any],
        occurred_at: datetime | None = None,
    ) -> RunEvent:
        assert_safe_remote_payload(payload)
        with self.transaction() as connection:
            return self._append_event_in_transaction(
                connection, run_id, event_type, payload, occurred_at or utc_now()
            )

    def _append_event_in_transaction(
        self,
        connection: sqlite3.Connection,
        run_id: str,
        event_type: str,
        payload: dict[str, Any],
        occurred_at: datetime,
    ) -> RunEvent:
        assert_safe_remote_payload(payload)
        row = connection.execute(
            "SELECT machine_id, status FROM runs WHERE run_id = ?", (run_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"unknown run: {run_id}")
        if row["status"] in TERMINAL_STATUSES:
            raise ValueError(f"run is already terminal: {run_id}")
        seq_row = connection.execute(
            "SELECT COALESCE(MAX(seq), 0) + 1 AS next_seq FROM events WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        seq = int(seq_row["next_seq"])
        event = RunEvent(
            event_id=str(uuid7()),
            run_id=run_id,
            machine_id=str(row["machine_id"]),
            seq=seq,
            type=event_type,  # type: ignore[arg-type]
            occurred_at=occurred_at,
            payload=payload,
        )
        event_json = event.model_dump_json()
        connection.execute(
            """
            INSERT INTO events(
                event_id, run_id, seq, event_type, event_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                event.event_id,
                run_id,
                seq,
                event_type,
                event_json,
                occurred_at.isoformat(),
            ),
        )
        updates: dict[str, Any] = {"updated_at": occurred_at.isoformat()}
        status = EVENT_STATUS.get(event_type)
        if status:
            updates["status"] = status
        if event_type == "run.started":
            updates["started_at"] = occurred_at.isoformat()
        if event_type.startswith("run.") and status in TERMINAL_STATUSES:
            updates["ended_at"] = occurred_at.isoformat()
            updates["exit_code"] = payload.get("exit_code")
        if "progress" in payload:
            updates["progress_json"] = json.dumps(payload["progress"])
        if "phase" in payload:
            updates["phase"] = payload["phase"]
        if "message" in payload:
            updates["safe_message"] = payload["message"]
        assignments = ", ".join(f"{name} = ?" for name in updates)
        connection.execute(
            f"UPDATE runs SET {assignments} WHERE run_id = ?",
            (*updates.values(), run_id),
        )
        return event

    def update_runtime(
        self, run_id: str, *, worker_pid: int | None = None, process_group: int | None = None
    ) -> None:
        updates: dict[str, Any] = {}
        if worker_pid is not None:
            updates["worker_pid"] = worker_pid
        if process_group is not None:
            updates["process_group"] = process_group
        if not updates:
            return
        assignments = ", ".join(f"{key} = ?" for key in updates)
        with self.connect() as connection:
            connection.execute(
                f"UPDATE runs SET {assignments} WHERE run_id = ?",
                (*updates.values(), run_id),
            )

    def mark_remote_initialized(self, run_id: str) -> None:
        with self.connect() as connection:
            connection.execute("UPDATE runs SET remote_initialized = 1 WHERE run_id = ?", (run_id,))

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        return self._run_dict(row) if row is not None else None

    def list_runs(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM runs ORDER BY updated_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [self._run_dict(row) for row in rows]

    @staticmethod
    def _run_dict(row: sqlite3.Row) -> dict[str, Any]:
        result = dict(row)
        result["progress"] = (
            json.loads(result.pop("progress_json")) if result.get("progress_json") else None
        )
        return result

    def pending_events(
        self, limit: int = 20, *, run_id: str | None = None, now: float | None = None
    ) -> list[RunEvent]:
        import time

        clauses = ["delivered = 0", "next_attempt_at <= ?"]
        parameters: list[Any] = [time.time() if now is None else now]
        if run_id:
            clauses.append("run_id = ?")
            parameters.append(run_id)
        parameters.append(limit)
        query = (
            "SELECT event_json FROM events WHERE "
            + " AND ".join(clauses)
            + " ORDER BY run_id, seq LIMIT ?"
        )
        with self.connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [RunEvent.model_validate_json(row["event_json"]) for row in rows]

    def mark_delivered(self, event_ids: list[str]) -> None:
        if not event_ids:
            return
        placeholders = ",".join("?" for _ in event_ids)
        with self.connect() as connection:
            connection.execute(
                f"UPDATE events SET delivered = 1, last_error = NULL "
                f"WHERE event_id IN ({placeholders})",
                event_ids,
            )

    def mark_failed(self, event_ids: list[str], error: str, delay_seconds: float) -> None:
        if not event_ids:
            return
        import time

        placeholders = ",".join("?" for _ in event_ids)
        with self.connect() as connection:
            connection.execute(
                f"""
                UPDATE events SET attempt_count = attempt_count + 1,
                    last_error = ?, next_attempt_at = ?
                WHERE event_id IN ({placeholders})
                """,
                (error[:300], time.time() + delay_seconds, *event_ids),
            )

    def event_rows(self, run_id: str) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT seq, event_type, event_json, delivered, attempt_count, last_error
                FROM events WHERE run_id = ? ORDER BY seq
                """,
                (run_id,),
            ).fetchall()
        return [dict(row) for row in rows]
