from __future__ import annotations

import json
import os
import socket
import threading
from collections.abc import Callable
from contextlib import suppress
from typing import Any


class RunBuoyError(RuntimeError):
    """Base class for failures in the local RunBuoy reporting channel."""


class RunBuoyUnavailableError(RunBuoyError):
    """The current process has no usable local RunBuoy Worker channel."""


class RunBuoyRejectedError(RunBuoyError):
    """The local Worker understood an event but rejected it."""


class RunBuoyProtocolError(RunBuoyError):
    """The local Worker response did not follow the SDK protocol."""


class RunBuoyValidationError(RunBuoyError):
    """An event could not be represented as a valid RunBuoy request."""


class RunBuoyInternalError(RunBuoyError):
    """An unexpected SDK implementation failure occurred."""


ErrorCallback = Callable[[RunBuoyError], None]


class Reporter:
    """Thread-safe client for the authenticated local Worker socket.

    A successful method call means only that the local Worker accepted the event.
    It makes no claim about server acceptance or iPhone delivery.
    """

    def __init__(
        self,
        socket_path: str | None,
        token: str | None,
        *,
        required: bool,
        on_error: ErrorCallback | None,
    ) -> None:
        self._socket_path = socket_path
        self._token = token
        self._required = required
        self._on_error = on_error
        self._lock = threading.Lock()
        self._send_lock = threading.Lock()
        self._enabled = bool(socket_path and token)
        self._callback_called = False

    @property
    def enabled(self) -> bool:
        with self._lock:
            return self._enabled

    def _disable(self, error: RunBuoyError) -> bool:
        callback: ErrorCallback | None = None
        with self._lock:
            self._enabled = False
            if not self._callback_called:
                self._callback_called = True
                callback = self._on_error
        if callback is not None:
            with suppress(Exception):
                callback(error)
        if self._required:
            raise error
        return False

    def _emit(self, kind: str, **payload: Any) -> bool:
        with self._lock:
            enabled = self._enabled and bool(self._socket_path and self._token)
        if not enabled:
            if self._required:
                raise RunBuoyUnavailableError("this process is not running under a RunBuoy Worker")
            return False

        with self._send_lock:
            with self._lock:
                enabled = self._enabled and bool(self._socket_path and self._token)
            if not enabled:
                if self._required:
                    raise RunBuoyUnavailableError(
                        "this process is not running under a RunBuoy Worker"
                    )
                return False
            return self._emit_once(kind, **payload)

    def _emit_once(self, kind: str, **payload: Any) -> bool:
        if self._socket_path is None or self._token is None:  # pragma: no cover - lock guard
            return self._disable(RunBuoyInternalError("Reporter context disappeared"))
        try:
            request = (
                json.dumps(
                    {"token": self._token, "kind": kind, **payload},
                    allow_nan=False,
                ).encode()
                + b"\n"
            )
        except (TypeError, ValueError):
            return self._disable(RunBuoyValidationError("RunBuoy event is not JSON serializable"))

        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                client.settimeout(2)
                client.connect(self._socket_path)
                client.sendall(request)
                response = bytearray()
                while b"\n" not in response:
                    chunk = client.recv(4096)
                    if not chunk:
                        break
                    response.extend(chunk)
                    if len(response) > 65_536:
                        raise RunBuoyProtocolError("RunBuoy Worker response is too large")
        except RunBuoyError as error:
            return self._disable(error)
        except (OSError, TimeoutError) as error:
            return self._disable(
                RunBuoyUnavailableError(f"local RunBuoy Worker is unavailable: {error}")
            )
        except Exception as error:  # pragma: no cover - defensive boundary
            return self._disable(
                RunBuoyInternalError(f"unexpected RunBuoy SDK failure: {type(error).__name__}")
            )

        try:
            if not response:
                raise RunBuoyProtocolError("RunBuoy Worker returned an empty response")
            decoded = json.loads(bytes(response).split(b"\n", 1)[0])
            if not isinstance(decoded, dict) or not isinstance(decoded.get("ok"), bool):
                raise RunBuoyProtocolError("RunBuoy Worker returned an invalid response")
            if not decoded["ok"]:
                reason = str(decoded.get("error", "unknown_error"))
                raise RunBuoyRejectedError(f"RunBuoy Worker rejected the event: {reason}")
        except RunBuoyError as error:
            return self._disable(error)
        except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError):
            return self._disable(RunBuoyProtocolError("RunBuoy Worker returned malformed JSON"))
        return True

    def progress(
        self,
        current: float,
        total: float,
        *,
        unit: str | None = None,
        phase: str | None = None,
        message: str | None = None,
    ) -> bool:
        return self._emit(
            "progress",
            current=current,
            total=total,
            unit=unit,
            phase=phase,
            message=message,
        )

    def phase(self, value: str) -> bool:
        return self._emit("phase", phase=value)

    def message(self, value: str) -> bool:
        return self._emit("message", message=value)

    def attention(self, value: str, *, status: str = "ACTION_REQUIRED") -> bool:
        return self._emit("attention", message=value, attention_status=status)


def get_reporter(
    required: bool = False,
    on_error: ErrorCallback | None = None,
) -> Reporter:
    """Return a reporter for the current process's local Worker context.

    The default is a disabled, silent reporter outside RunBuoy. Strict callers can
    request an immediate typed error with ``required=True``.
    """

    reporter = Reporter(
        os.environ.get("RUNBUOY_EVENT_SOCKET"),
        os.environ.get("RUNBUOY_EVENT_TOKEN"),
        required=required,
        on_error=on_error,
    )
    if required and not reporter.enabled:
        reporter._disable(
            RunBuoyUnavailableError("this process is not running under a RunBuoy Worker")
        )
    return reporter


_default_lock = threading.Lock()
_default_context: tuple[str | None, str | None] | None = None
_default_reporter: Reporter | None = None


def _get_default_reporter() -> Reporter:
    global _default_context, _default_reporter
    context = (
        os.environ.get("RUNBUOY_EVENT_SOCKET"),
        os.environ.get("RUNBUOY_EVENT_TOKEN"),
    )
    with _default_lock:
        if _default_reporter is None or context != _default_context:
            _default_context = context
            _default_reporter = Reporter(*context, required=False, on_error=None)
        return _default_reporter


def progress(
    current: float,
    total: float,
    *,
    unit: str | None = None,
    phase: str | None = None,
    message: str | None = None,
) -> bool:
    return _get_default_reporter().progress(
        current,
        total,
        unit=unit,
        phase=phase,
        message=message,
    )


def phase(value: str) -> bool:
    return _get_default_reporter().phase(value)


def message(value: str) -> bool:
    return _get_default_reporter().message(value)


def attention(value: str, *, status: str = "ACTION_REQUIRED") -> bool:
    return _get_default_reporter().attention(value, status=status)
