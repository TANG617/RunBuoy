from __future__ import annotations

from pathlib import Path

from runbuoy.config import Config, CredentialStore, ensure_machine_identity, load_config
from runbuoy.paths import AppPaths


def test_default_server_uses_production_https_url() -> None:
    assert str(Config().server_url) == "https://api.runbuoy.cloud/"


def test_credential_file_fallback_is_mode_0600(tmp_path: Path, monkeypatch: object) -> None:
    monkeypatch.setenv("RUNBUOY_DISABLE_KEYRING", "1")  # type: ignore[attr-defined]
    paths = AppPaths(tmp_path / "config", tmp_path / "data", tmp_path / "state", tmp_path / "cache")
    store = CredentialStore(paths)
    store.set("machine_credential", "secret")
    assert store.get("machine_credential") == "secret"
    assert paths.credential_file.stat().st_mode & 0o077 == 0


def test_machine_identity_is_generated_once_and_persisted(tmp_path: Path) -> None:
    paths = AppPaths(
        tmp_path / "config",
        tmp_path / "data",
        tmp_path / "state",
        tmp_path / "cache",
    )
    first = ensure_machine_identity(paths, Config())
    second = ensure_machine_identity(paths, load_config(paths))
    assert first.machine_id is not None
    assert first.machine_id == second.machine_id
    assert paths.config_file.stat().st_mode & 0o077 == 0
