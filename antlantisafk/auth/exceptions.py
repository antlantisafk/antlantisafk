"""Typed exceptions for every stage of the authentication chain."""

from __future__ import annotations


class AuthError(Exception):
    """Base class for authentication failures."""


class MicrosoftAuthError(AuthError):
    """Microsoft device-code flow or token refresh failure."""


class XboxAuthError(AuthError):
    """Xbox Live (XBL) or XSTS authentication failure."""


class MinecraftAuthError(AuthError):
    """Minecraft services authentication or profile fetch failure."""


class TokenRefreshError(AuthError):
    """Silent refresh-token renewal failed; interactive login required."""
