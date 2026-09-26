"""Tests for antlantisafk.config (load, save, round-trip, validation)."""

from __future__ import annotations

import pytest

from antlantisafk.config import AppConfig, ConfigError, ConfigManager


class TestDefaults:
    def test_defaults_are_safe(self):
        cfg = AppConfig()
        assert cfg.server_address == ""
        assert cfg.server_port == 25565
        assert cfg.minecraft_version == "auto"
        assert cfg.join_message_enabled is False  # opt-in only
        assert cfg.join_message == ""
        assert cfg.minimize_to_tray is False
        assert cfg.azure_client_id == ""


class TestRoundTrip:
    def test_save_then_load(self, isolated_appdata):
        cfg = AppConfig(
            server_address="Play.Example.NET",
            server_port=25566,
            minecraft_version="1.20.4",
            reconnect_delay_seconds=7,
            max_reconnect_attempts=3,
            minimize_to_tray=True,
        )
        mgr = ConfigManager()
        mgr.save(cfg)
        assert mgr.path.exists()

        loaded = mgr.load()
        assert loaded.server_address == "play.example.net"
        assert loaded.server_port == 25566
        assert loaded.minecraft_version == "1.20.4"
        assert loaded.reconnect_delay_seconds == 7
        assert loaded.max_reconnect_attempts == 3
        assert loaded.minimize_to_tray is True

    def test_unknown_keys_preserved(self, isolated_appdata):
        mgr = ConfigManager()
        cfg = AppConfig(server_address="a.example.net")
        mgr.save(cfg)
        # Simulate a future version writing an extra key.
        text = mgr.path.read_text(encoding="utf-8")
        text += "\nfuture_field = 42\n"
        mgr.path.write_text(text, encoding="utf-8")

        loaded = mgr.load()
        assert loaded._unknown.get("future_field") == 42
        mgr.save(loaded)  # round-trips without loss
        assert "future_field = 42" in mgr.path.read_text(encoding="utf-8")

    def test_missing_file_uses_defaults(self, isolated_appdata):
        mgr = ConfigManager()
        cfg = mgr.load()
        assert cfg == AppConfig()

    def test_corrupt_file_uses_defaults(self, isolated_appdata):
        mgr = ConfigManager()
        mgr.path.parent.mkdir(parents=True, exist_ok=True)
        mgr.path.write_text("this is not [ valid toml", encoding="utf-8")
        cfg = mgr.load()
        assert cfg == AppConfig()

    def test_invalid_values_fall_back_to_defaults(self, isolated_appdata):
        mgr = ConfigManager()
        mgr.path.parent.mkdir(parents=True, exist_ok=True)
        mgr.path.write_text('server_address = "bad host!"\n', encoding="utf-8")
        cfg = mgr.load()
        assert cfg == AppConfig()


class TestValidation:
    def test_rejects_bad_address(self):
        with pytest.raises(ConfigError):
            AppConfig(server_address="bad host!").validate()

    def test_rejects_bad_port(self):
        with pytest.raises(ConfigError):
            AppConfig(server_port=99999).validate()

    def test_rejects_bad_version(self):
        with pytest.raises(ConfigError):
            AppConfig(minecraft_version="banana").validate()

    def test_rejects_bad_delay(self):
        with pytest.raises(ConfigError):
            AppConfig(reconnect_delay_seconds=-5).validate()

    def test_rejects_bad_attempts(self):
        with pytest.raises(ConfigError):
            AppConfig(max_reconnect_attempts=99999).validate()

    def test_rejects_long_join_message(self):
        with pytest.raises(ConfigError):
            AppConfig(join_message="x" * 300).validate()


class TestSecretHygiene:
    def test_refuses_secret_like_keys(self, isolated_appdata):
        cfg = AppConfig(server_address="a.example.net")
        cfg._unknown["access_token"] = "should-never-be-saved"
        mgr = ConfigManager()
        with pytest.raises(ConfigError):
            mgr.assert_no_secrets(cfg)

    def test_config_file_never_contains_token_words(self, isolated_appdata):
        cfg = AppConfig(server_address="a.example.net",
                        azure_client_id="00000000-0000-0000-0000-000000000000")
        mgr = ConfigManager()
        mgr.save(cfg)
        text = mgr.path.read_text(encoding="utf-8").lower()
        for forbidden in ("refresh_token", "access_token", "password",
                          "session_id"):
            assert forbidden not in text
