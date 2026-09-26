"""Minecraft connection subpackage for AntlantisAFK.

Architecture: the Python GUI never speaks the Minecraft protocol itself. It
launches a small Node.js worker (``mineflayer`` via ``minecraft-protocol``)
and exchanges newline-delimited JSON commands/events over the worker's stdin/
stdout. The worker uses the **Microsoft access token our Python auth layer
already obtained** — never a password, never a raw session ID.

The worker responds ONLY to keep-alives. It sends no movement, chat, or
interactions of any kind; this is enforced in ``worker/afk_worker.js`` and is
the entire point of this application.
"""

from .session import AfkSession, SessionState
from .exceptions import (
    ConnectionError as McConnectionError,
    KeepAliveTimeoutError,
    WorkerNotFoundError,
    WorkerStartupError,
)

__all__ = [
    "AfkSession",
    "SessionState",
    "McConnectionError",
    "KeepAliveTimeoutError",
    "WorkerNotFoundError",
    "WorkerStartupError",
]
