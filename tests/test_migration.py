"""Tests for the legacy %APPDATA% data migration (pre-rebrand folder name)."""

from __future__ import annotations

from pathlib import Path

from antlantisafk.constants import (
    LEGACY_APPDATA_NAME,
    appdata_dir,
    migrate_legacy_appdata,
)


def _make_legacy_data(base: Path) -> Path:
    legacy = base / LEGACY_APPDATA_NAME
    legacy.mkdir(parents=True, exist_ok=True)
    (legacy / "config.toml").write_text(
        'server_address = "old.example.net"\n', encoding="utf-8"
    )
    logs = legacy / "logs"
    logs.mkdir()
    (logs / "antlantisafk.log").write_text("old log line\n", encoding="utf-8")
    (legacy / "refresh_token.bin").write_bytes(b"AAFKFAKEBLOB")
    return legacy


def test_migration_moves_all_data(isolated_appdata):
    legacy = _make_legacy_data(isolated_appdata)
    assert migrate_legacy_appdata() is True

    new_dir = appdata_dir()
    assert (new_dir / "config.toml").read_text(encoding="utf-8").startswith(
        'server_address = "old.example.net"'
    )
    assert (new_dir / "logs" / "antlantisafk.log").exists()
    assert (new_dir / "refresh_token.bin").read_bytes() == b"AAFKFAKEBLOB"
    assert not legacy.exists()  # emptied and removed


def test_migration_is_noop_when_no_legacy(isolated_appdata):
    assert migrate_legacy_appdata() is False


def test_migration_does_not_clobber_newer_files(isolated_appdata):
    legacy = _make_legacy_data(isolated_appdata)
    # Newer config already exists in the destination; must be preserved.
    new_dir = appdata_dir()
    (new_dir / "config.toml").write_text(
        'server_address = "new.example.net"\n', encoding="utf-8"
    )

    migrate_legacy_appdata()

    text = (new_dir / "config.toml").read_text(encoding="utf-8")
    assert "new.example.net" in text
    assert "old.example.net" not in text
    # Other items still migrated.
    assert (new_dir / "refresh_token.bin").exists()
    # Legacy folder keeps only the skipped file, so it survives.
    assert legacy.exists()


def test_new_folder_uses_new_name(isolated_appdata):
    appdata_dir()
    assert (isolated_appdata / "AtlantisAFK").is_dir()
