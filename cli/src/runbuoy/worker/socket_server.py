from __future__ import annotations

import hmac
import json
import os
import socket
import threading
from collections.abc import Callable
from contextlib import suppress
from pathlib import Path
from typing import Any

SocketHandler = Callable[[dict[str, Any]], dict[str, Any]]


class EventSocketServer:
    def __init__(
        self,
        path: Path,
        token: str,
        handler: SocketHandler,
    ) -> None:
        self.path = path
        self.token = token
        self.handler = handler
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._thread: threading.Thread | None = None
        self._socket: socket.socket | None = None
        self._startup_error: OSError | None = None

    def start(self) -> None:
        self._thread = threading.Thread(
            target=self._serve,
            name="runbuoy-event-socket",
            daemon=True,
        )
        self._thread.start()
        if not self._ready.wait(5):
            raise RuntimeError("local event socket did not start")
        if self._startup_error is not None:
            raise RuntimeError("local event socket could not bind") from self._startup_error

    def close(self) -> None:
        self._stop.set()
        if self._socket is not None:
            with suppress(OSError):
                self._socket.close()
        if self._thread is not None:
            self._thread.join(timeout=2)
        self.path.unlink(missing_ok=True)

    def _serve(self) -> None:
        self.path.unlink(missing_ok=True)
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._socket = server
        try:
            server.bind(str(self.path))
        except OSError as error:
            self._startup_error = error
            self._ready.set()
            server.close()
            return
        os.chmod(self.path, 0o600)
        server.listen(8)
        server.settimeout(0.2)
        self._ready.set()
        while not self._stop.is_set():
            try:
                connection, _ = server.accept()
            except TimeoutError:
                continue
            except OSError:
                break
            with connection:
                connection.settimeout(2)
                response = self._handle_connection(connection)
                connection.sendall(json.dumps(response).encode() + b"\n")
        try:
            server.close()
        finally:
            self.path.unlink(missing_ok=True)

    def _handle_connection(self, connection: socket.socket) -> dict[str, Any]:
        data = bytearray()
        try:
            while len(data) <= 65_536:
                chunk = connection.recv(4096)
                if not chunk:
                    break
                data.extend(chunk)
                if b"\n" in chunk:
                    break
            if len(data) > 65_536:
                return {"ok": False, "error": "request_too_large"}
            request = json.loads(bytes(data).split(b"\n", 1)[0])
            supplied = str(request.pop("token", ""))
            if not hmac.compare_digest(supplied, self.token):
                return {"ok": False, "error": "unauthorized"}
            return self.handler(request)
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return {"ok": False, "error": "invalid_request"}
