"""Application-wide constants and filesystem paths for AntlantisAFK.

All persistent data lives under ``%APPDATA%\\AntlantisAFK`` on Windows so the
app works both from source and from a frozen PyInstaller executable.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from . import APP_NAME

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
    """Return (creating if needed) the per-user application data directory."""
    base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    path = Path(base) / APP_NAME
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

#: Service name used in Windows Credential Manager via ``keyring``.
KEYRING_SERVICE: str = APP_NAME
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

#: Name of the Win32 mutex (or lock file) enforcing a single running instance.
SINGLE_INSTANCE_MUTEX: str = "AntlantisAFK-{fingerprint}-SingleInstanceMutex"
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
