"""Secure storage for the Microsoft OAuth refresh token.

Strategy:
1. Preferred: ``keyring`` (Windows Credential Manager on Windows).
2. Fallback: Windows DPAPI via ``win32crypt`` (pywin32), stored as a local
   encrypted blob only readable by the current Windows user.

Only the refresh token is persisted. Access tokens live in memory for the
current session only. A logout deletes every stored credential.

This module NEVER accepts raw session IDs and NEVER stores passwords — those
restrictions are enforced by the callers and the GUI which offer no input path
for them.
"""

from __future__ import annotations

import base64
import logging
import secrets
from abc import ABC, abstractmethod

from ..constants import (
    KEYRING_SERVICE,
    KEYRING_USERNAME,
    refresh_token_file,
)

logger = logging.getLogger(__name__)

#: Prefix stored alongside DPAPI blobs so we can identify our own format.
_BLOB_MAGIC: bytes = b"AAFKE1"


class TokenStoreError(Exception):
    """Raised when tokens cannot be stored, read, or deleted securely."""


class TokenStore(ABC):
    """Abstract storage for the single refresh token."""

    @abstractmethod
    def save_refresh_token(self, token: str) -> None:
        """Persist the refresh token securely."""

    @abstractmethod
    def load_refresh_token(self) -> str | None:
        """Return the stored refresh token, or None if absent."""

    @abstractmethod
    def delete_credentials(self) -> None:
        """Delete every stored credential (logout / delete credentials)."""


# ---------------------------------------------------------------------------
# keyring-backed store
# ---------------------------------------------------------------------------


class KeyringTokenStore(TokenStore):
    """Refresh-token storage via the ``keyring`` library (Credential Manager)."""

    def __init__(self) -> None:
        global keyring  # noqa: PLW0603
        try:
            import keyring  # type: ignore[import-untyped]
        except ImportError as exc:  # pragma: no cover
            raise TokenStoreError(
                "The 'keyring' package is required for secure token storage. "
                "Install it with: pip install keyring"
            ) from exc
        self._keyring = keyring

    def save_refresh_token(self, token: str) -> None:
        try:
            self._keyring.set_password(KEYRING_SERVICE, KEYRING_USERNAME, token)
            logger.info("Refresh token stored in system credential manager.")
        except Exception as exc:  # keyring raises various backend errors
            raise TokenStoreError(f"Could not store refresh token securely: {exc}") from exc

    def load_refresh_token(self) -> str | None:
        try:
            token = self._keyring.get_password(KEYRING_SERVICE, KEYRING_USERNAME)
        except Exception as exc:
            raise TokenStoreError(f"Could not read refresh token: {exc}") from exc
        return token or None

    def delete_credentials(self) -> None:
        try:
            self._keyring.delete_password(KEYRING_SERVICE, KEYRING_USERNAME)
            logger.info("Refresh token deleted from credential manager.")
        except Exception:
            # Most backends raise when the entry does not exist; that is fine.
            logger.info("No stored refresh token to delete (or already removed).")


# ---------------------------------------------------------------------------
# DPAPI fallback store (Windows only)
# ---------------------------------------------------------------------------


class DPAPITokenStore(TokenStore):
    """Fallback storage using Windows DPAPI (pywin32) with a local blob.

    DPAPI encrypts to the current Windows user account, so the file is
    unreadable on other machines or by other users. A random per-install salt
    is prepended to defeat trivial blob-equivalence comparisons.
    """

    def __init__(self) -> None:
        try:
            import win32crypt  # type: ignore[import-untyped]  # noqa: F401
        except ImportError as exc:  # pragma: no cover
            raise TokenStoreError(
                "DPAPI fallback requires the 'pywin32' package. "
                "Install it with: pip install pywin32"
            ) from exc
        self._salt_file = refresh_token_file().with_suffix(".salt")
        self._salt = self._load_or_create_salt()

    def _load_or_create_salt(self) -> bytes:
        if self._salt_file.exists():
            data = self._salt_file.read_bytes()
            if len(data) >= 32:
                return data
        salt = secrets.token_bytes(32)
        self._salt_file.parent.mkdir(parents=True, exist_ok=True)
        self._salt_file.write_bytes(salt)
        return salt

    def _crypt_protect(self, data: bytes) -> bytes:
        import win32crypt  # type: ignore[import-untyped]

        # CRYPTPROTECT_UI_FORBIDDEN: no UI popups from a background service.
        desc = "AntlantisAFK refresh token"
        # Signature: (DataIn, Name, OptionalEntropy, Reserved, PromptStruct, Flags)
        # pywin32 requires Reserved to be None (not 0).
        result = win32crypt.CryptProtectData(
            data, desc, self._salt, None, None, 0x1  # CRYPTPROTECT_UI_FORBIDDEN
        )
        # Older pywin32 returns (description, blob); newer returns blob bytes.
        if isinstance(result, tuple):
            blob = result[1] if len(result) == 2 else result[0]
        else:
            blob = result
        return bytes(blob)

    def _crypt_unprotect(self, blob: bytes) -> bytes:
        import win32crypt  # type: ignore[import-untyped]

        # Signature differs from CryptProtectData: (DataIn, OptionalEntropy,
        # Reserved, PromptStruct, Flags) — no description parameter. pywin32
        # requires Reserved to be None. Entropy must match the protect call.
        result = win32crypt.CryptUnprotectData(
            blob, self._salt, None, None, 0x1  # CRYPTPROTECT_UI_FORBIDDEN
        )
        # Older pywin32 returns (description, data); newer returns data bytes.
        if isinstance(result, tuple):
            data = result[1] if len(result) == 2 else result[0]
        else:
            data = result
        return bytes(data)

    def save_refresh_token(self, token: str) -> None:
        path = refresh_token_file()
        try:
            blob = self._crypt_protect(token.encode("utf-8"))
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(_BLOB_MAGIC + base64.b64encode(blob))
            logger.info("Refresh token encrypted with DPAPI and stored locally.")
        except OSError as exc:
            raise TokenStoreError(f"Could not write token file: {exc}") from exc

    def load_refresh_token(self) -> str | None:
        path = refresh_token_file()
        if not path.exists():
            return None
        try:
            raw = path.read_bytes()
            if not raw.startswith(_BLOB_MAGIC):
                raise TokenStoreError("Token file is corrupt or from another app.")
            blob = base64.b64decode(raw[len(_BLOB_MAGIC):])
            return self._crypt_unprotect(blob).decode("utf-8")
        except (OSError, ValueError) as exc:
            raise TokenStoreError(f"Could not read token file: {exc}") from exc

    def delete_credentials(self) -> None:
        removed = False
        for f in (refresh_token_file(), self._salt_file):
            if f.exists():
                try:
                    f.unlink()
                    removed = True
                except OSError as exc:
                    logger.warning("Could not delete %s: %s", f, exc)
        if removed:
            logger.info("Local token files deleted.")


def create_token_store() -> TokenStore:
    """Return the best available secure token store for this platform.

    Prefers ``keyring`` (Credential Manager); falls back to DPAPI on Windows.
    Raises :class:`TokenStoreError` if neither is available.
    """
    try:
        store = KeyringTokenStore()
        # Probe that the backend actually works (some Linux headless setups
        # import fine but fail at runtime).
        store.load_refresh_token()
        return store
    except TokenStoreError:
        pass
    from ..constants import is_windows

    if is_windows():
        logger.info("Falling back to DPAPI token storage.")
        return DPAPITokenStore()
    raise TokenStoreError(
        "No secure token storage available. Install 'keyring' (and on Windows "
        "optionally 'pywin32')."
    )
