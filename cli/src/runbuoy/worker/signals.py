from __future__ import annotations

import os
import signal
import time
from collections.abc import Callable

SignalSender = Callable[[int, signal.Signals], None]


def escalate_process_group(
    process_group: int,
    *,
    grace_seconds: float,
    is_alive: Callable[[], bool],
    send_signal: SignalSender | None = None,
    wait: Callable[[float], None] = time.sleep,
) -> list[signal.Signals]:
    """Send SIGINT, SIGTERM, then SIGKILL to a local target process group."""
    sender = send_signal or os.killpg
    sent: list[signal.Signals] = []
    for current_signal in (signal.SIGINT, signal.SIGTERM, signal.SIGKILL):
        if not is_alive():
            break
        try:
            sender(process_group, current_signal)
        except ProcessLookupError:
            break
        sent.append(current_signal)
        if current_signal != signal.SIGKILL:
            wait(grace_seconds)
    return sent
