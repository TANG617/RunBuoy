from __future__ import annotations

import json
import signal
import socket
from pathlib import Path
from uuid import uuid4

from runbuoy.worker.signals import escalate_process_group
from runbuoy.worker.socket_server import EventSocketServer


def request(path: Path, value: dict[str, object]) -> dict[str, object]:
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.connect(str(path))
        client.sendall(json.dumps(value).encode() + b"\n")
        return json.loads(client.recv(4096))


def test_event_socket_auth_and_permissions(tmp_path: Path) -> None:
    del tmp_path
    path = Path("/tmp") / f"runbuoy-test-{uuid4().hex}.sock"
    received: list[dict[str, object]] = []
    handler = lambda event: received.append(event) or {"ok": True}  # noqa: E731
    server = EventSocketServer(path, "expected", handler)
    server.start()
    try:
        assert request(path, {"token": "wrong", "kind": "phase"}) == {
            "ok": False,
            "error": "unauthorized",
        }
        assert request(path, {"token": "expected", "kind": "phase"}) == {"ok": True}
        assert received == [{"kind": "phase"}]
        assert path.stat().st_mode & 0o077 == 0
    finally:
        server.close()


def test_signal_escalation_stops_when_process_exits() -> None:
    alive = True
    sent: list[signal.Signals] = []

    def sender(_group: int, value: signal.Signals) -> None:
        nonlocal alive
        sent.append(value)
        if value == signal.SIGTERM:
            alive = False

    result = escalate_process_group(
        123,
        grace_seconds=0.1,
        is_alive=lambda: alive,
        send_signal=sender,
        wait=lambda _seconds: None,
    )
    assert result == [signal.SIGINT, signal.SIGTERM]
    assert sent == [signal.SIGINT, signal.SIGTERM]
