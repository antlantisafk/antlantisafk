"""Configuration loading, saving, validation, and safe migration.

Configuration is stored as TOML in ``%APPDATA%\\AntlantisAFK\\config.toml``.
The config file NEVER contains tokens, passwords, or session identifiers —
those are handled exclusively by :mod:`antlantisafk.security.token_store`.

Every field is validated; unknown fields are preserved so a future version can
read a config written by an older version without data loss.
"""

from __future__ import annotations

import logging
import re
import tomllib
from dataclasses import dataclass, asdict, field, fields
from pathlib import Path
from typing import Any

from .constants import config_path
from .utils.validators import (
    ValidationError,
    validate_minecraft_version,
    validate_port,
    validate_server_address,
)

try:  # Python 3.11+
    import tomli_w  # type: ignore[import-untyped]
except ImportError:  # pragma: no cover - dev dependency fallback
    tomli_w = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


class ConfigError(Exception):
    """Raised when the configuration file cannot be read, parsed, or written."""


@dataclass
class AppConfig:
    """User configuration for AntlantisAFK.

    Attributes:
        server_address: Hostname or IP of the Minecraft server.
        server_port: TCP port of the server (1-65535, default 25565).
        minecraft_version: Minecraft version to report, or "auto" for the
            latest supported protocol.
        reconnect_delay_seconds: Base delay for exponential reconnect backoff.
        max_reconnect_attempts: Stop reconnecting after this many consecutive
            failures (0 means retry forever).
        minimize_to_tray: Hide to the system tray instead of the taskbar when
            the window is minimized.
        join_message: Optional message sent once after joining. DISABLED by
            default; the user must opt in. This app refuses to send repeated
            messages or chat spam.
        version: Internal schema version for future migrations.
    """

    server_address: str = ""
    server_port: int = 25565
    minecraft_version: str = "auto"
    reconnect_delay_seconds: int = 5
    max_reconnect_attempts: int = 10
    minimize_to_tray: bool = False
    join_message: str = ""
    join_message_enabled: bool = False
    #: Azure AD application (client) ID used for the device-code flow.
    #: Not a secret. Prefer the ANTLANTISAFK_CLIENT_ID environment variable
    #: for packaged builds; the config field is the documented fallback.
    azure_client_id: str = ""
    version: int = 1

    # Extra keys read from disk that we do not understand yet; round-tripped
    # so upgrading/downgrading does not silently destroy user settings.
    _unknown: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    # -- validation ---------------------------------------------------------

    def validate(self, require_server_address: bool = True) -> None:
        """Validate all fields, raising :class:`ConfigError` on bad values.

        Args:
            require_server_address: When True (session start), the server
                address must be non-empty. Config-file saves pass False so
                settings like the Azure client ID can be persisted before
                the user has chosen a server.
        """
        try:
            if self.server_address.strip() or require_server_address:
                self.server_address = validate_server_address(self.server_address)
            self.server_port = validate_port(self.server_port)
            self.minecraft_version = validate_minecraft_version(self.minecraft_version)
        except ValidationError as exc:
            raise ConfigError(str(exc)) from exc

        if not (0 <= int(self.reconnect_delay_seconds) <= 600):
            raise ConfigError(
                f"reconnect_delay_seconds must be between 0 and 600 "
                f"(got {self.reconnect_delay_seconds})."
            )
        self.reconnect_delay_seconds = int(self.reconnect_delay_seconds)

        if not (0 <= int(self.max_reconnect_attempts) <= 1000):
            raise ConfigError(
                f"max_reconnect_attempts must be between 0 and 1000 "
                f"(got {self.max_reconnect_attempts})."
            )
        self.max_reconnect_attempts = int(self.max_reconnect_attempts)

        self.minimize_to_tray = bool(self.minimize_to_tray)
        # join_message may be empty; long messages are capped to something
        # sane. Spam prevention: the app sends it at most once per join.
        if len(self.join_message) > 256:
            raise ConfigError("join_message must be at most 256 characters.")
        self.azure_client_id = (self.azure_client_id or "").strip()
        if self.azure_client_id and not re.fullmatch(r"[0-9a-fA-F-]{8,64}", self.azure_client_id):
            raise ConfigError(
                "azure_client_id should be the GUID from Azure Portal "
                "(e.g. 00000000-0000-0000-0000-000000000000)."
            )

    # -- serialization ------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Return a TOML-ready dict of all fields plus preserved unknowns."""
        data: dict[str, Any] = asdict(self)
        data.pop("_unknown", None)
        data.update(self._unknown)
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AppConfig":
        """Build an :class:`AppConfig` from a parsed TOML dict.

        Unknown keys are preserved in ``_unknown`` for lossless round-trips.
        """
        known = {f.name for f in fields(cls) if f.name != "_unknown"}
        unknown = {k: v for k, v in data.items() if k not in known}
        kwargs = {k: v for k, v in data.items() if k in known}
        cfg = cls(**kwargs)  # type: ignore[arg-type]
        cfg._unknown = unknown
        return cfg


class ConfigManager:
    """Load, validate, and save :class:`AppConfig` instances."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or config_path()

    # -- loading ------------------------------------------------------------

    def load(self) -> AppConfig:
        """Load the config file, falling back to defaults on any problem.

        A missing file is not an error (first run). A corrupt or invalid file
        is logged and replaced by defaults so the app always starts.
        """
        if not self.path.exists():
            logger.info("No config file at %s; using defaults.", self.path)
            return AppConfig()

        try:
            raw = self.path.read_bytes()
            data = tomllib.loads(raw.decode("utf-8"))
        except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
            logger.error("Failed to parse config %s: %s. Using defaults.", self.path, exc)
            return AppConfig()

        cfg = AppConfig.from_dict(data)
        try:
            cfg.validate()
        except ConfigError as exc:
            logger.error("Invalid config values: %s. Using defaults.", exc)
            return AppConfig()
        logger.info("Loaded configuration from %s.", self.path)
        return cfg

    # -- saving -------------------------------------------------------------

    def save(self, cfg: AppConfig) -> None:
        """Validate and atomically write the configuration to disk.

        An empty server address is allowed here (validated strictly again at
        session start); everything else must still be valid.
        """
        cfg.validate(require_server_address=False)
        if tomli_w is None:
            raise ConfigError(
                "Writing configuration requires the 'tomli-w' package. "
                "Install it with: pip install tomli-w"
            )
        data = cfg.to_dict()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        try:
            tmp.write_text(tomli_w.dumps(data), encoding="utf-8")
            tmp.replace(self.path)
        except OSError as exc:
            tmp.unlink(missing_ok=True)
            raise ConfigError(f"Could not save configuration: {exc}") from exc
        logger.info("Saved configuration to %s.", self.path)

    # -- token hygiene ------------------------------------------------------

    def assert_no_secrets(self, cfg: AppConfig) -> None:
        """Defence-in-depth check that no secret-like keys are persisted."""
        forbidden = ("token", "secret", "password", "session", "refresh", "access")
        for key in cfg.to_dict():
            if any(f in key.lower() for f in forbidden):
                raise ConfigError(
                    f"Refusing to save config containing secret-like key '{key}'. "
                    "Tokens are stored only in Windows Credential Manager."
                )
