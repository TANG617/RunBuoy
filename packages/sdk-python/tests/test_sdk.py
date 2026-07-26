from __future__ import annotations

import json
import os
import socket
import threading
from pathlib import Path
from uuid import uuid4

from runbuoy import progress


def test_progress_sends_authenticated_local_event(tmp_path: Path) -> None:
    del tmp_path
    path = Path("/tmp") / f"runbuoy-sdk-test-{uuid4().hex}.sock"
    received: list[dict[str, object]] = []
    ready = threading.Event()

    def server() -> None:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as listener:
            listener.bind(str(path))
            listener.listen(1)
            ready.set()
            connection, _ = listener.accept()
            with connection:
                received.append(json.loads(connection.recv(4096)))
                connection.sendall(b'{"ok":true}\n')

    thread = threading.Thread(target=server)
    thread.start()
    assert ready.wait(2)
    os.environ["RUNBUOY_EVENT_SOCKET"] = str(path)
    os.environ["RUNBUOY_EVENT_TOKEN"] = "ephemeral"
    try:
        progress(3, 10, phase="work")
    finally:
        os.environ.pop("RUNBUOY_EVENT_SOCKET")
        os.environ.pop("RUNBUOY_EVENT_TOKEN")
    thread.join(2)
    path.unlink(missing_ok=True)
    assert received == [
        {
            "token": "ephemeral",
            "kind": "progress",
            "current": 3,
            "total": 10,
            "unit": None,
            "phase": "work",
            "message": None,
        }
    ]
