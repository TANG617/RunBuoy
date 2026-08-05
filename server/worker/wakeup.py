from __future__ import annotations

import time
from contextlib import suppress
from typing import Any

from sqlalchemy.engine import make_url


class OutboxWakeup:
    """Wait for committed PostgreSQL outbox notifications with a polling fallback."""

    channel = "runbuoy_push_outbox"

    def __init__(self, database_url: str) -> None:
        self.database_url = database_url
        self.connection: Any | None = None
        if database_url.startswith("postgresql"):
            self._connect()

    def _connect(self) -> None:
        try:
            import psycopg

            url = make_url(self.database_url).set(drivername="postgresql")
            self.connection = psycopg.connect(
                url.render_as_string(hide_password=False),
                autocommit=True,
            )
            self.connection.execute(f"LISTEN {self.channel}")
        except Exception:
            self.connection = None

    def wait(self, timeout: float) -> None:
        bounded_timeout = max(0.0, timeout)
        if self.connection is None:
            time.sleep(min(bounded_timeout, 0.1))
            if self.database_url.startswith("postgresql"):
                self._connect()
            return
        try:
            for _notification in self.connection.notifies(
                timeout=bounded_timeout,
                stop_after=1,
            ):
                return
        except Exception:
            self.close()
            self._connect()

    def close(self) -> None:
        if self.connection is not None:
            with suppress(Exception):
                self.connection.close()
        self.connection = None
