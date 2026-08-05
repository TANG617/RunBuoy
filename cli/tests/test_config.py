from __future__ import annotations

import json
from pathlib import Path

from runbuoy.config import (
    Config,
    CredentialStore,
    RunBuoyRegion,
    ensure_machine_identity,
    load_config,
)
from runbuoy.paths import AppPaths


def test_default_server_uses_production_https_url() -> None:
    assert Config().region is RunBuoyRegion.GLOBAL
    assert str(Config().server_url) == "https://api.runbuoy.cloud/"
    assert Config().upload_interval_seconds == 0.25
    assert Config().batch_size == 100


def test_regions_map_to_stable_hosted_urls() -> None:
    assert RunBuoyRegion.GLOBAL.server_url == "https://api.runbuoy.cloud"
    assert RunBuoyRegion.CHINA.server_url == "https://api-cn.runbuoy.cloud"


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


def test_legacy_upload_defaults_migrate_without_overwriting_custom_values(tmp_path: Path) -> None:
    paths = AppPaths(
        tmp_path / "config",
        tmp_path / "data",
        tmp_path / "state",
        tmp_path / "cache",
    )
    paths.ensure()
    paths.config_file.write_text(
        json.dumps(
            {
                "upload_interval_seconds": 1.0,
                "batch_size": 20,
                "cancel_grace_seconds": 7,
            }
        )
    )

    migrated = load_config(paths)

    assert migrated.schema_version == 2
    assert migrated.upload_interval_seconds == 0.25
    assert migrated.batch_size == 100
    assert migrated.cancel_grace_seconds == 7
    assert json.loads(paths.config_file.read_text())["schema_version"] == 2
