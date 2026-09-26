"""AFK session state machine with exponential-backoff reconnection.

The session owns the worker bridge and implements the reconnect policy:

- Exponential backoff starting at the configured delay, capped at 10 minutes.
- Respects ``max_reconnect_attempts`` (0 = retry forever).
- Never automates gameplay; the worker answers keep-alives only.
- All callbacks fire on a worker thread; the GUI must marshal to the Qt main
  loop itself (see ``antlantisafk.gui.main_window``).

Thread-safety: all public methods may be called from any thread; internal
state is guarded by a lock and stop/start races are serialised.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from enum import Enum, auto
from typing import Callable

from ..auth.manager import AuthResult
from ..config import AppConfig
from .exceptions import AuthRejectedError, MinecraftSessionError
from .worker_bridge import WorkerBridge

logger = logging.getLogger(__name__)

#: Hard cap for exponential backoff regardless of configuration.
MAX_BACKOFF_CAP: int = 600  # seconds (10 minutes)


class SessionState(Enum):
    """Detailed session state (finer than the GUI's ConnectionStatus)."""

    IDLE = auto()
    CONNECTING = auto()
    CONNECTED = auto()
    WAITING_RETRY = auto()
    STOPPING = auto()
    ERROR = auto()


@dataclass
class SessionSnapshot:
    """Thread-safe point-in-time view of session state for the GUI."""

    state: SessionState
    connection_status_text: str
    connected_since: float | None
    uptime_seconds: int
    reconnect_count: int
    attempt: int
    next_retry_at: float | None
    last_error: str


class AfkSession:
    """Manage one authenticated AFK connection to one Minecraft server.

    Args:
        config: Validated application configuration.
        auth_result: A successful :class:`AuthResult` (username, UUID, token).
        bridge: The worker bridge (one per session is created by default).
        on_change: Optional callback invoked on every state change with a
            :class:`SessionSnapshot`.
    """

    def __init__(
        self,
        config: AppConfig,
        auth_result: AuthResult,
        bridge: WorkerBridge | None = None,
        on_change: Callable[[SessionSnapshot], None] | None = None,
    ) -> None:
        self._config = config
        self._auth = auth_result
        self._bridge = bridge or WorkerBridge()
        self._on_change = on_change

        self._lock = threading.RLock()
        self._state = SessionState.IDLE
        self._connected_since: float | None = None
        self._reconnect_count = 0
        self._attempt = 0
        self._next_retry_at: float | None = None
        self._last_error: str = ""
        self._stop_requested = threading.Event()
        self._retry_timer: threading.Timer | None = None

        # Worker events we care about.
        self._bridge.on("connected", self._on_worker_connected)
        self._bridge.on("end", self._on_worker_end)
        self._bridge.on("error", self._on_worker_error)
        self._bridge.on("kicked", self._on_worker_kicked)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start connecting (spawns the worker and begins the join flow)."""
        with self._lock:
            if self._state not in (SessionState.IDLE, SessionState.ERROR):
                return
            self._stop_requested.clear()
            self._attempt = 0
            self._reconnect_count = 0
            self._state = SessionState.CONNECTING
        self._notify()
        self._connect_once()

    def stop(self) -> None:
        """Stop the session and disconnect. Safe to call from any thread."""
        with self._lock:
            if self._state == SessionState.IDLE:
                return
            self._stop_requested.set()
            self._state = SessionState.STOPPING
            timer = self._retry_timer
            self._retry_timer = None
        self._notify()
        if timer is not None:
            timer.cancel()
        self._graceful_disconnect()

    def snapshot(self) -> SessionSnapshot:
        """Return a consistent snapshot of the current state."""
        with self._lock:
            uptime = (
                int(time.time() - self._connected_since)
                if self._connected_since is not None
                else 0
            )
            status = {
                SessionState.IDLE: "Disconnected",
                SessionState.CONNECTING: "Connecting…",
                SessionState.CONNECTED: "Connected",
                SessionState.WAITING_RETRY: "Reconnecting…",
                SessionState.STOPPING: "Disconnecting…",
                SessionState.ERROR: "Error",
            }[self._state]
            return SessionSnapshot(
                state=self._state,
                connection_status_text=status,
                connected_since=self._connected_since,
                uptime_seconds=uptime,
                reconnect_count=self._reconnect_count,
                attempt=self._attempt,
                next_retry_at=self._next_retry_at,
                last_error=self._last_error,
            )

    # ------------------------------------------------------------------
    # Connection flow
    # ------------------------------------------------------------------

    def _connect_once(self) -> None:
        """One connection attempt via the worker; schedules retry on failure."""
        if self._stop_requested.is_set():
            return
        with self._lock:
            attempt = self._attempt + 1
            self._attempt = attempt
            self._connected_since = None
        logger.info(
            "Connection attempt %s to %s:%s (version %s).",
            attempt, self._config.server_address, self._config.server_port,
            self._config.minecraft_version,
        )
        self._notify()

        try:
            self._bridge.start()
            self._bridge.send_token_handshake(
                self._auth.access_token, self._auth.username, self._auth.uuid
            )
            self._bridge.request(
                "connect",
                {
                    "host": self._config.server_address,
                    "port": int(self._config.server_port),
                    "version": self._config.minecraft_version,
                    "joinMessage": self._config.join_message
                    if self._config.join_message_enabled
                    else "",
                },
                timeout=120.0,
            )
            # Success path: the worker emits 'connected' once the PLAY state
            # begins; treat the request ack as provisional success too.
            with self._lock:
                self._connected_since = time.time()
                self._state = SessionState.CONNECTED
            logger.info("Connected to %s:%s.", self._config.server_address,
                        self._config.server_port)
            self._notify()
        except AuthRejectedError:
            self._fail("The server rejected this account's login. The token "
                       "may have expired — log in again.")
        except MinecraftSessionError as exc:
            self._schedule_retry(str(exc))
        except Exception as exc:  # noqa: BLE001 - reported, never crashes
            logger.exception("Unexpected error during connection.")
            self._schedule_retry(str(exc))

    def _schedule_retry(self, error: str) -> None:
        """Handle a failed attempt: give up, or schedule a backoff retry."""
        max_attempts = int(self._config.max_reconnect_attempts)
        with self._lock:
            attempt = self._attempt
            self._last_error = error
            self._connected_since = None
            self._state = SessionState.ERROR
            self._next_retry_at = None

        logger.warning("Connection failed: %s", error)

        if self._stop_requested.is_set():
            self._notify()
            return
        if 0 < max_attempts <= attempt:
            logger.error(
                "Gave up after %s reconnect attempts; stopping.", attempt
            )
            self._notify()
            return

        delay = self._backoff_delay(attempt)
        with self._lock:
            self._reconnect_count += 1
            self._state = SessionState.WAITING_RETRY
            self._next_retry_at = time.time() + delay
        logger.info(
            "Reconnect attempt %s in %ss (max %s).",
            attempt + 1, delay, max_attempts if max_attempts > 0 else "∞",
        )
        self._notify()
        timer = threading.Timer(delay, self._retry_connect)
        timer.daemon = True
        with self._lock:
            self._retry_timer = timer
        timer.start()

    def _retry_connect(self) -> None:
        with self._lock:
            self._retry_timer = None
            if self._state == SessionState.WAITING_RETRY and not self._stop_requested.is_set():
                self._state = SessionState.CONNECTING
        self._notify()
        self._connect_once()

    def _backoff_delay(self, attempt: int) -> int:
        """Exponential backoff: base * 2^(attempt-1), capped."""
        base = max(1, int(self._config.reconnect_delay_seconds))
        return min(base * (2 ** max(0, attempt - 1)), MAX_BACKOFF_CAP)

    def _fail(self, message: str) -> None:
        """Terminal failure: stop retrying (usually an auth problem)."""
        with self._lock:
            self._last_error = message
            self._state = SessionState.ERROR
            self._connected_since = None
            self._next_retry_at = None
        logger.error("Session failed permanently: %s", message)
        self._graceful_disconnect()
        self._notify()

    # ------------------------------------------------------------------
    # Worker event handlers (worker thread)
    # ------------------------------------------------------------------

    def _on_worker_connected(self, data: dict) -> None:
        with self._lock:
            self._connected_since = time.time()
            self._state = SessionState.CONNECTED
            self._attempt = 0
        logger.info("Worker reports in-game connection established.")
        self._notify()

    def _on_worker_end(self, data: dict) -> None:
        reason = str(data.get("reason", "unknown"))
        logger.info("Worker connection ended: %s", reason)
        with self._lock:
            was_connected = self._state == SessionState.CONNECTED
            self._connected_since = None
        if self._stop_requested.is_set():
            return
        if was_connected:
            # Clean disconnect mid-session: reconnect from attempt 1.
            with self._lock:
                self._attempt = 0
        self._schedule_retry(f"Disconnected by server: {reason}")

    def _on_worker_error(self, data: dict) -> None:
        message = str(data.get("message", "worker error"))
        logger.warning("Worker error: %s", message)
        with self._lock:
            if self._state in (SessionState.CONNECTED,):
                # The worker will usually follow with an 'end' event; let it
                # drive the retry to avoid double attempts.
                return
        self._schedule_retry(message)

    def _on_worker_kicked(self, data: dict) -> None:
        reason = str(data.get("reason", "kicked"))
        logger.warning("Kicked from server: %s", reason)
        with self._lock:
            self._connected_since = None
        if not self._stop_requested.is_set():
            self._schedule_retry(f"Kicked: {reason}")

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _graceful_disconnect(self) -> None:
        """Ask the worker to disconnect and shut the bridge down."""
        try:
            if self._bridge.is_running():
                self._bridge.request("disconnect", {}, timeout=10.0)
        except Exception:  # noqa: BLE001
            logger.debug("Disconnect request failed; continuing teardown.")
        try:
            self._bridge.stop()
        except Exception:  # noqa: BLE001
            logger.debug("Worker stop raised during teardown.", exc_info=True)
        with self._lock:
            if self._state == SessionState.STOPPING:
                self._state = SessionState.IDLE
                self._next_retry_at = None
        self._notify()

    def _notify(self) -> None:
        """Emit a snapshot to the registered callback (never raises)."""
        if self._on_change is None:
            return
        try:
            self._on_change(self.snapshot())
        except Exception:  # noqa: BLE001
            logger.exception("Session change callback raised.")
