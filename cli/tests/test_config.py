from __future__ import annotations

from pathlib import Path

from runbuoy.config import CredentialStore
from runbuoy.paths import AppPaths


def test_credential_file_fallback_is_mode_0600(tmp_path: Path, monkeypatch: object) -> None:
    monkeypatch.setenv("RUNBUOY_DISABLE_KEYRING", "1")  # type: ignore[attr-defined]
    paths = AppPaths(tmp_path / "config", tmp_path / "data", tmp_path / "state", tmp_path / "cache")
    store = CredentialStore(paths)
    store.set("machine_credential", "secret")
    assert store.get("machine_credential") == "secret"
    assert paths.credential_file.stat().st_mode & 0o077 == 0
