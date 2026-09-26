"""Application-wide constants and filesystem paths for AntlantisAFK.

All persistent data lives under ``%APPDATA%\\AntlantisAFK`` on Windows so the
app works both from source and from a frozen PyInstaller executable.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

from . import APP_ID, APP_NAME

# ---------------------------------------------------------------------------
# Identity / branding
# ---------------------------------------------------------------------------

SUPPORT_URL: str = "https://github.com/antlantisafk/antlantisafk"
DISCLAIMER_URL: str = (
    "https://github.com/antlantisafk/antlantisafk#legal-and-safety-disclaimer"
)

# ---------------------------------------------------------------------------
# Microsoft device-code login
# ---------------------------------------------------------------------------

#: Azure AD application (client) ID identifying AntlantisAFK to Microsoft.
#: This is NOT a secret (it is baked into every public desktop app); the
#: secure part of the flow is the per-user login in the browser.
DEFAULT_AZURE_CLIENT_ID: str = "81e20f08-163a-42f1-bf44-529ceac17aba"

# ---------------------------------------------------------------------------
# Filesystem layout (%APPDATA%\AntlantisAFK)
# ---------------------------------------------------------------------------


def appdata_dir() -> Path:
    """Return (creating if needed) the per-user application data directory.

    Uses the stable internal APP_ID so branding renames never orphan a
    user's config, logs, or stored credentials.
    """
    base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    path = Path(base) / APP_ID
    path.mkdir(parents=True, exist_ok=True)
    return path


def config_dir() -> Path:
    """Directory holding the TOML configuration file."""
    return appdata_dir()


def config_path() -> Path:
    """Full path of the TOML configuration file."""
    return config_dir() / "config.toml"


def logs_dir() -> Path:
    """Return (creating if needed) the logs directory."""
    path = appdata_dir() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def log_file_path() -> Path:
    """Full path of the rotating application log file."""
    return logs_dir() / "antlantisafk.log"


def refresh_token_file() -> Path:
    """Path of the DPAPI-encrypted refresh-token blob (fallback storage)."""
    return appdata_dir() / "refresh_token.bin"


# ---------------------------------------------------------------------------
# Secure token storage identifiers
# ---------------------------------------------------------------------------

#: Service name used in Windows Credential Manager via ``keyring``
#: (stable internal id, survives branding renames).
KEYRING_SERVICE: str = APP_ID
#: Account/username entry under the service in the credential manager.
KEYRING_USERNAME: str = "refresh_token"

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

LOG_MAX_BYTES: int = 5 * 1024 * 1024  # rotate at 5 MB
LOG_BACKUP_COUNT: int = 3  # keep 3 backups
LOG_FORMAT: str = "%(asctime)s [%(levelname)-8s] %(name)s: %(message)s"

# ---------------------------------------------------------------------------
# Single-instance coordination
# ---------------------------------------------------------------------------

#: Name of the Win32 mutex (or lock file) enforcing a single running
#: instance (stable internal id).
SINGLE_INSTANCE_MUTEX: str = "AtlantisAFK-{fingerprint}-SingleInstanceMutex"
#: Local TCP port used to ask an already-running instance to show its window.
FOCUS_PORT_BASE: int = 49000

# ---------------------------------------------------------------------------
# Runtime detection
# ---------------------------------------------------------------------------


def is_frozen() -> bool:
    """True when running from a PyInstaller-built executable."""
    return getattr(sys, "frozen", False)


def is_windows() -> bool:
    """True when running on Windows."""
    return sys.platform.startswith("win")


# ---------------------------------------------------------------------------
# Legacy data migration (pre-rebrand folder name)
# ---------------------------------------------------------------------------

#: Folder name used by builds before the AtlantisAFK rebrand.
LEGACY_APPDATA_NAME: str = "AntlantisAFK"


def migrate_legacy_appdata() -> bool:
    """Move pre-rebrand ``%APPDATA%\\AntlantisAFK`` data to the new name.

    Copies config, logs, and DPAPI token blobs into the new folder (existing
    files in the destination win, so a newer install is never downgraded),
    then removes the empty legacy folder. Safe to call on every startup.

    Returns:
        True when any data was migrated.
    """
    base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    legacy = Path(base) / LEGACY_APPDATA_NAME
    if not legacy.exists() or legacy.resolve() == appdata_dir().resolve():
        return False

    moved: list[str] = []
    for item in legacy.iterdir():
        dest = appdata_dir() / item.name
        if dest.exists():
            continue  # destination already has newer data; keep it
        try:
            shutil.move(str(item), str(dest))
            moved.append(item.name)
        except OSError:
            continue
    try:
        if not any(legacy.iterdir()):
            legacy.rmdir()
    except OSError:
        pass
    if moved:
        import logging

        logging.getLogger(APP_NAME).info(
            "Migrated legacy data from %s: %s", legacy.name, ", ".join(moved)
        )
    return bool(moved)
