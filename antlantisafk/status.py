"""Shared status enums used by the auth layer, session layer, and GUI."""

from __future__ import annotations

from enum import Enum, auto


class AccountStatus(Enum):
    """High-level account/auth state shown in the GUI."""

    NOT_LOGGED_IN = auto()
    LOGGING_IN = auto()
    LOGGED_IN = auto()
    TOKEN_EXPIRED = auto()
    ERROR = auto()


class ConnectionStatus(Enum):
    """High-level connection state shown in the GUI."""

    DISCONNECTED = auto()
    CONNECTING = auto()
    CONNECTED = auto()
    RECONNECTING = auto()
    ERROR = auto()


#: Human-readable text for each account status (GUI + tray).
ACCOUNT_STATUS_TEXT: dict[AccountStatus, str] = {
    AccountStatus.NOT_LOGGED_IN: "Not logged in",
    AccountStatus.LOGGING_IN: "Logging in…",
    AccountStatus.LOGGED_IN: "Logged in",
    AccountStatus.TOKEN_EXPIRED: "Token expired",
    AccountStatus.ERROR: "Error",
}

#: Human-readable text for each connection status (GUI + tray).
CONNECTION_STATUS_TEXT: dict[ConnectionStatus, str] = {
    ConnectionStatus.DISCONNECTED: "Disconnected",
    ConnectionStatus.CONNECTING: "Connecting…",
    ConnectionStatus.CONNECTED: "Connected",
    ConnectionStatus.RECONNECTING: "Reconnecting…",
    ConnectionStatus.ERROR: "Error",
}
