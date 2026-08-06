from __future__ import annotations

import json
import socket
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

import pytest

from runbuoy import (
    RunBuoyInternalError,
    RunBuoyProtocolError,
    RunBuoyRejectedError,
    RunBuoyUnavailableError,
    RunBuoyValidationError,
    get_reporter,
    progress,
)


@contextmanager
def worker_socket(
    response: bytes | Callable[[dict[str, object]], bytes],
) -> Iterator[tuple[Path, list[dict[str, object]]]]:
    path = Path("/tmp") / f"runbuoy-sdk-test-{uuid4().hex}.sock"
    received: list[dict[str, object]] = []
    ready = threading.Event()
    stop = threading.Event()

    def server() -> None:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as listener:
            listener.bind(str(path))
            listener.listen(16)
            listener.settimeout(0.1)
            ready.set()
            while not stop.is_set():
                try:
                    connection, _ = listener.accept()
                except TimeoutError:
                    continue
                with connection:
                    request = json.loads(connection.recv(65_536))
                    received.append(request)
                    reply = response(request) if callable(response) else response
                    connection.sendall(reply)

    thread = threading.Thread(target=server)
    thread.start()
    assert ready.wait(2)
    try:
        yield path, received
    finally:
        stop.set()
        thread.join(2)
        path.unlink(missing_ok=True)


def test_reporter_is_silent_noop_without_runbuoy_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("RUNBUOY_EVENT_SOCKET", raising=False)
    monkeypatch.delenv("RUNBUOY_EVENT_TOKEN", raising=False)
    errors: list[Exception] = []

    reporter = get_reporter(on_error=errors.append)

    assert reporter.enabled is False
    assert reporter.progress(1, 2) is False
    assert reporter.phase("work") is False
    assert reporter.message("still working") is False
    assert reporter.attention("check this") is False
    assert errors == []


def test_required_reporter_raises_without_context(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("RUNBUOY_EVENT_SOCKET", raising=False)
    monkeypatch.delenv("RUNBUOY_EVENT_TOKEN", raising=False)

    with pytest.raises(RunBuoyUnavailableError):
        get_reporter(required=True)


def test_progress_returns_true_after_local_worker_ack(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with worker_socket(b'{"ok":true}\n') as (path, received):
        monkeypatch.setenv("RUNBUOY_EVENT_SOCKET", str(path))
        monkeypatch.setenv("RUNBUOY_EVENT_TOKEN", "ephemeral")
        reporter = get_reporter()

        assert reporter.progress(3, 10, phase="work") is True
        assert reporter.enabled is True

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


@pytest.mark.parametrize(
    ("response", "error_type"),
    [
        (b'{"ok":false,"error":"stale_progress"}\n', RunBuoyRejectedError),
        (b"not-json\n", RunBuoyProtocolError),
        (b'{"accepted":true}\n', RunBuoyProtocolError),
    ],
)
def test_best_effort_failure_disables_and_calls_back_once(
    response: bytes,
    error_type: type[Exception],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    errors: list[Exception] = []
    with worker_socket(response) as (path, _received):
        monkeypatch.setenv("RUNBUOY_EVENT_SOCKET", str(path))
        monkeypatch.setenv("RUNBUOY_EVENT_TOKEN", "ephemeral")
        reporter = get_reporter(on_error=errors.append)

        assert reporter.phase("first") is False
        assert reporter.phase("second") is False

    assert reporter.enabled is False
    assert len(errors) == 1
    assert isinstance(errors[0], error_type)


def test_unavailable_socket_and_callback_failure_are_swallowed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RUNBUOY_EVENT_SOCKET", str(tmp_path / "missing.sock"))
    monkeypatch.setenv("RUNBUOY_EVENT_TOKEN", "ephemeral")
    callback_count = 0

    def broken_callback(_error: Exception) -> None:
        nonlocal callback_count
        callback_count += 1
        raise RuntimeError("callback failure")

    reporter = get_reporter(on_error=broken_callback)
    assert reporter.message("hello") is False
    assert reporter.message("again") is False
    assert callback_count == 1


def test_error_callback_can_safely_observe_disabled_reporter(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RUNBUOY_EVENT_SOCKET", str(tmp_path / "missing.sock"))
    monkeypatch.setenv("RUNBUOY_EVENT_TOKEN", "ephemeral")
    observed: list[tuple[bool, bool]] = []
    reporter = None

    def callback(_error: Exception) -> None:
        assert reporter is not None
        observed.append((reporter.enabled, reporter.phase("callback diagnostic")))

    reporter = get_reporter(on_error=callback)
    assert reporter.message("hello") is False
    assert observed == [(False, False)]


def test_required_reporter_raises_typed_worker_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with worker_socket(b'{"ok":false,"error":"invalid_event"}\n') as (path, _received):
        monkeypatch.setenv("RUNBUOY_EVENT_SOCKET", str(path))
        monkeypatch.setenv("RUNBUOY_EVENT_TOKEN", "ephemeral")
        reporter = get_reporter(required=True)

        with pytest.raises(RunBuoyRejectedError):
            reporter.message("bad")


def test_non_json_value_is_a_validation_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RUNBUOY_EVENT_SOCKET", "/tmp/not-used.sock")
    monkeypatch.setenv("RUNBUOY_EVENT_TOKEN", "ephemeral")
    errors: list[Exception] = []
    reporter = get_reporter(on_error=errors.append)

    assert reporter.progress(float("nan"), 2) is False
    assert isinstance(errors[0], RunBuoyValidationError)


def test_unexpected_sdk_failure_is_typed_and_best_effort(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RUNBUOY_EVENT_SOCKET", "/tmp/not-used.sock")
    monkeypatch.setenv("RUNBUOY_EVENT_TOKEN", "ephemeral")
    monkeypatch.setattr("runbuoy.sdk.socket.socket", lambda *_args, **_kwargs: 1 / 0)
    errors: list[Exception] = []
    reporter = get_reporter(on_error=errors.append)

    assert reporter.message("hello") is False
    assert isinstance(errors[0], RunBuoyInternalError)


def test_reporter_disable_and_callback_once_are_thread_safe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RUNBUOY_EVENT_SOCKET", "/tmp/runbuoy-missing-thread-test.sock")
    monkeypatch.setenv("RUNBUOY_EVENT_TOKEN", "ephemeral")
    errors: list[Exception] = []
    reporter = get_reporter(on_error=errors.append)
    results: list[bool] = []
    threads = [
        threading.Thread(target=lambda: results.append(reporter.phase("work"))) for _ in range(12)
    ]

    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert results == [False] * 12
    assert len(errors) == 1


def test_top_level_default_reporter_tracks_environment_changes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("RUNBUOY_EVENT_SOCKET", raising=False)
    monkeypatch.delenv("RUNBUOY_EVENT_TOKEN", raising=False)
    assert progress(1, 2) is False

    with worker_socket(b'{"ok":true}\n') as (path, received):
        monkeypatch.setenv("RUNBUOY_EVENT_SOCKET", str(path))
        monkeypatch.setenv("RUNBUOY_EVENT_TOKEN", "ephemeral")
        assert progress(1, 2) is True

    assert len(received) == 1
