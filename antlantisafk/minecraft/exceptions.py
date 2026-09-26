"""Exceptions for the Minecraft connection layer."""

from __future__ import annotations


class MinecraftSessionError(Exception):
    """Base class for AFK session errors."""


class WorkerNotFoundError(MinecraftSessionError):
    """The Node.js runtime or the worker script could not be found."""


class WorkerStartupError(MinecraftSessionError):
    """The worker process failed to start or crashed before connecting."""


class ConnectionError(MinecraftSessionError):  # noqa: A001 - deliberate shadow
    """Connecting to the Minecraft server failed."""


class KeepAliveTimeoutError(MinecraftSessionError):
    """The server stopped responding to keep-alives."""


class AuthRejectedError(MinecraftSessionError):
    """The server rejected the login (auth/session error)."""
