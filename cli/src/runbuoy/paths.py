from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path


def _xdg_path(variable: str, mac_subpath: str, fallback: str) -> Path:
    explicit = os.environ.get(variable)
    if explicit:
        return Path(explicit).expanduser() / "runbuoy"
    if sys.platform == "darwin":
        return Path.home() / "Library" / mac_subpath / "RunBuoy"
    return Path.home() / fallback / "runbuoy"


@dataclass(frozen=True)
class AppPaths:
    config: Path
    data: Path
    state: Path
    cache: Path

    @classmethod
    def discover(cls) -> AppPaths:
        root = os.environ.get("RUNBUOY_HOME")
        if root:
            base = Path(root).expanduser()
            return cls(base / "config", base / "data", base / "state", base / "cache")
        return cls(
            _xdg_path("XDG_CONFIG_HOME", "Application Support", ".config"),
            _xdg_path("XDG_DATA_HOME", "Application Support", ".local/share"),
            _xdg_path("XDG_STATE_HOME", "Application Support", ".local/state"),
            _xdg_path("XDG_CACHE_HOME", "Caches", ".cache"),
        )

    def ensure(self) -> None:
        for path in (self.config, self.data, self.state, self.cache):
            path.mkdir(mode=0o700, parents=True, exist_ok=True)
            path.chmod(0o700)

    @property
    def database(self) -> Path:
        return self.state / "runbuoy.sqlite3"

    @property
    def config_file(self) -> Path:
        return self.config / "config.json"

    @property
    def credential_file(self) -> Path:
        return self.config / "credentials.json"

    def run_dir(self, run_id: str) -> Path:
        result = self.state / "runs" / run_id
        result.mkdir(mode=0o700, parents=True, exist_ok=True)
        result.chmod(0o700)
        return result

    def event_socket(self, run_id: str) -> Path:
        # Darwin limits AF_UNIX paths to 104 bytes. Keep ephemeral sockets in a
        # short, owner-only directory even when XDG/RUNBUOY_HOME is deeply nested.
        explicit = os.environ.get("RUNBUOY_SOCKET_DIR")
        directory = Path(explicit) if explicit else Path("/tmp") / f"runbuoy-{os.getuid()}"
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        directory.chmod(0o700)
        return directory / f"{run_id}.sock"
