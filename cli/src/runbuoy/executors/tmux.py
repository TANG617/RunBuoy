from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


class TmuxUnavailableError(RuntimeError):
    pass


class TmuxExecutor:
    @staticmethod
    def available() -> bool:
        return shutil.which("tmux") is not None

    def start(self, session: str, manifest_path: Path) -> None:
        if not self.available():
            raise TmuxUnavailableError("tmux is required; install tmux and retry")
        environment = os.environ.copy()
        command = [
            "tmux",
            "new-session",
            "-d",
            "-s",
            session,
            "-e",
            f"RUNBUOY_MANIFEST={manifest_path}",
            "-e",
            f"RUNBUOY_PYTHON={sys.executable}",
        ]
        # A long-lived tmux server has its own stale environment. Explicitly copy
        # only RunBuoy/XDG path selectors needed to find the same local database.
        for name in (
            "RUNBUOY_HOME",
            "RUNBUOY_SOCKET_DIR",
            "RUNBUOY_DISABLE_KEYRING",
            "XDG_CONFIG_HOME",
            "XDG_DATA_HOME",
            "XDG_STATE_HOME",
            "XDG_CACHE_HOME",
        ):
            value = environment.get(name)
            if value is not None:
                command.extend(("-e", f"{name}={value}"))
        command.append('exec "$RUNBUOY_PYTHON" -m runbuoy _worker --manifest "$RUNBUOY_MANIFEST"')
        result = subprocess.run(
            command,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode:
            raise RuntimeError(f"tmux could not start worker: {result.stderr.strip()}")

    def attach(self, session: str) -> int:
        return subprocess.call(["tmux", "attach-session", "-t", session])

    def exists(self, session: str) -> bool:
        result = subprocess.run(
            ["tmux", "has-session", "-t", session],
            capture_output=True,
            check=False,
        )
        return result.returncode == 0
