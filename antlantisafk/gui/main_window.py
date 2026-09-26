"""Main application window for AntlantisAFK.

One account, one server, strictly passive AFK. The window coordinates:

- Account card: device-code login/logout, username, account status.
- Server card: address, port, version, start/stop.
- Status card: connection state, uptime, reconnect count.
- Log card: scrolling INFO+ log mirroring the file log.
- Settings card: reconnect delay, max retries, minimize-to-tray.

A QSystemTrayIcon offers Show/Hide, Start/Stop AFK, and Exit. The session
runs on worker threads; all state updates are marshalled onto the Qt main
loop via signals.
"""

from __future__ import annotations

import logging
import threading
import time

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from .. import APP_NAME, APP_VERSION
from ..auth.manager import AuthResult, MinecraftAuthenticator
from ..auth.exceptions import TokenRefreshError
from ..config import AppConfig, ConfigError, ConfigManager
from ..constants import DISCLAIMER_URL
from ..minecraft import AfkSession
from ..minecraft.session import SessionSnapshot, SessionState
from ..security.token_store import TokenStore
from ..status import (
    ACCOUNT_STATUS_TEXT,
    CONNECTION_STATUS_TEXT,
    AccountStatus,
    ConnectionStatus,
)
from ..utils.validators import validate_minecraft_version  # noqa: F401 (docs)
from .login_dialog import LoginDialog
from .theme import COLORS, build_app_icon
from .widgets import Card, LogPanel, StatusPill

logger = logging.getLogger(__name__)

_ACCOUNT_PILL_COLOR: dict[AccountStatus, str] = {
    AccountStatus.NOT_LOGGED_IN: "idle",
    AccountStatus.LOGGING_IN: "busy",
    AccountStatus.LOGGED_IN: "ok",
    AccountStatus.TOKEN_EXPIRED: "warn",
    AccountStatus.ERROR: "err",
}

_CONN_PILL_COLOR: dict[ConnectionStatus, str] = {
    ConnectionStatus.DISCONNECTED: "idle",
    ConnectionStatus.CONNECTING: "busy",
    ConnectionStatus.CONNECTED: "ok",
    ConnectionStatus.RECONNECTING: "warn",
    ConnectionStatus.ERROR: "err",
}


class MainWindow(QMainWindow):
    """Primary application window (single instance, enforced in ``main``)."""

    # Cross-thread signals: emitted from worker threads, delivered on the
    # Qt main loop because the receivers live there.
    _account_changed = Signal(object)      # AccountStatus
    _profile_changed = Signal(str)         # username ("" when logged out)
    _session_changed = Signal(object)      # SessionSnapshot
    _session_stopped = Signal()

    def __init__(self, config: AppConfig, config_manager: ConfigManager,
                 token_store: TokenStore, client_id: str = "") -> None:
        super().__init__()
        self._config = config
        self._config_manager = config_manager
        self._token_store = token_store
        self._client_id = client_id

        self._authenticator: MinecraftAuthenticator | None = None
        self._auth_result: AuthResult | None = None
        self._session: AfkSession | None = None
        self._account_status = AccountStatus.NOT_LOGGED_IN

        self._ui_timer = QTimer(self)
        self._ui_timer.setInterval(1000)
        self._ui_timer.timeout.connect(self._tick)
        self._ui_timer.start()

        self._build_ui()
        self._init_tray()

        self._account_changed.connect(self._on_account_changed)
        self._profile_changed.connect(self._on_profile_changed)
        self._session_changed.connect(self._on_session_changed)
        self._session_stopped.connect(self._on_session_stopped)

        self._restore_session_silently()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        self.setWindowTitle(f"{APP_NAME} {APP_VERSION}")
        self.setMinimumSize(600, 700)
        self.resize(720, 820)
        self.setMaximumWidth(900)  # never full-bleed on wide monitors

        central = QWidget()
        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        body = QWidget()
        body.setMaximumWidth(860)
        body_layout = QVBoxLayout(body)
        body_layout.setSpacing(14)
        body_layout.setContentsMargins(20, 18, 20, 14)
        outer.addWidget(body, 0, Qt.AlignHCenter)
        scroll = body_layout

        # Header -----------------------------------------------------------
        header = QVBoxLayout()
        header.setSpacing(2)
        title = QLabel(APP_NAME)
        title.setObjectName("Title")
        subtitle = QLabel(
            "Single-account AFK companion for Minecraft: Java Edition — "
            "keep-alives only, no gameplay automation."
        )
        subtitle.setObjectName("Subtitle")
        header.addWidget(title)
        header.addWidget(subtitle)
        scroll.addLayout(header)

        # Account card -------------------------------------------------------
        account_card = Card("Account — one account only")
        form1 = QFormLayout()
        form1.setHorizontalSpacing(14)
        form1.setVerticalSpacing(12)
        self._username_label = QLabel("—")
        self._username_label.setStyleSheet("font-size: 15px; font-weight: 600;")
        self._account_pill = StatusPill("Not logged in", "idle")
        self._login_btn = QPushButton("Login with Microsoft")
        self._login_btn.setObjectName("Primary")
        self._login_btn.clicked.connect(self._on_login)
        self._logout_btn = QPushButton("Logout / Delete Credentials")
        self._logout_btn.setObjectName("Danger")
        self._logout_btn.clicked.connect(self._on_logout)
        row = QHBoxLayout()
        row.addWidget(self._login_btn)
        row.addWidget(self._logout_btn)
        row.addStretch(1)
        form1.addRow("Profile:", self._username_label)
        form1.addRow("Status:", self._account_pill)
        form1.addRow(row)
        account_card.body().addLayout(form1)
        scroll.addWidget(account_card)

        # Server card --------------------------------------------------------
        server_card = Card("Server — one server only")
        form2 = QFormLayout()
        form2.setHorizontalSpacing(14)
        form2.setVerticalSpacing(12)
        self._server_edit = QLineEdit(self._config.server_address)
        self._server_edit.setPlaceholderText("play.example.net or 203.0.113.10")
        self._port_spin = QSpinBox()
        self._port_spin.setRange(1, 65535)
        self._port_spin.setValue(int(self._config.server_port))
        self._version_edit = QLineEdit(self._config.minecraft_version)
        self._version_edit.setPlaceholderText("auto")
        self._version_edit.setToolTip(
            "'auto' negotiates the server's version, or enter e.g. 1.20.4."
        )
        form2.addRow("Address:", self._server_edit)
        form2.addRow("Port:", self._port_spin)
        form2.addRow("Minecraft version:", self._version_edit)
        server_card.body().addLayout(form2)
        scroll.addWidget(server_card)

        # Control row --------------------------------------------------------
        control_row = QHBoxLayout()
        self._start_btn = QPushButton("Start AFK")
        self._start_btn.setObjectName("Primary")
        self._start_btn.clicked.connect(self._on_start_clicked)
        self._stop_btn = QPushButton("Stop")
        self._stop_btn.setObjectName("Danger")
        self._stop_btn.clicked.connect(self._on_stop_clicked)
        self._stop_btn.setEnabled(False)
        control_row.addWidget(self._start_btn)
        control_row.addWidget(self._stop_btn)
        control_row.addStretch(1)
        scroll.addLayout(control_row)

        # Status card ----------------------------------------------------------
        status_card = Card("Status")
        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(12)
        grid.addWidget(QLabel("Connection:"), 0, 0)
        self._conn_pill = StatusPill("Disconnected", "idle")
        grid.addWidget(self._conn_pill, 0, 1, Qt.AlignLeft)
        grid.addWidget(QLabel("Uptime:"), 0, 2)
        self._uptime_label = QLabel("00:00:00")
        grid.addWidget(self._uptime_label, 0, 3, Qt.AlignLeft)
        grid.addWidget(QLabel("Reconnects:"), 1, 0)
        self._reconnects_label = QLabel("0")
        grid.addWidget(self._reconnects_label, 1, 1, Qt.AlignLeft)
        grid.addWidget(QLabel("Next retry:"), 1, 2)
        self._retry_label = QLabel("—")
        grid.addWidget(self._retry_label, 1, 3, Qt.AlignLeft)
        status_card.body().addLayout(grid)
        scroll.addWidget(status_card)

        # Log card ------------------------------------------------------------
        log_card = Card("Log")
        self._log_panel = LogPanel()
        self._log_panel.attach_to_logger()
        self._log_panel.setMinimumHeight(170)
        log_card.body().addWidget(self._log_panel)
        scroll.addWidget(log_card)

        # Settings card ---------------------------------------------------------
        settings_card = Card("Settings")
        form3 = QFormLayout()
        form3.setHorizontalSpacing(14)
        form3.setVerticalSpacing(12)
        self._delay_spin = QSpinBox()
        self._delay_spin.setRange(0, 600)
        self._delay_spin.setValue(int(self._config.reconnect_delay_seconds))
        self._delay_spin.setSuffix(" s")
        self._retries_spin = QSpinBox()
        self._retries_spin.setRange(0, 1000)
        self._retries_spin.setValue(int(self._config.max_reconnect_attempts))
        self._retries_spin.setSpecialValueText("∞ (retry forever)")
        self._tray_check = QCheckBox("Minimize to system tray while connected")
        self._tray_check.setChecked(bool(self._config.minimize_to_tray))
        form3.addRow("Reconnect delay:", self._delay_spin)
        form3.addRow("Max reconnect attempts:", self._retries_spin)
        form3.addRow(self._tray_check)
        settings_card.body().addLayout(form3)
        scroll.addWidget(settings_card)

        # Footer ---------------------------------------------------------------
        footer = QHBoxLayout()
        disclaimer = QLabel(
            f"<a href='{DISCLAIMER_URL}'>AFK clients may violate server rules "
            "— use only on servers where AFK is explicitly allowed, and only "
            "with your own account.</a>"
        )
        disclaimer.setObjectName("Disclaimer")
        disclaimer.setOpenExternalLinks(True)
        disclaimer.setWordWrap(True)
        footer.addWidget(disclaimer, 1)
        version = QLabel(f"v{APP_VERSION}")
        version.setStyleSheet(f"color: {COLORS['muted']};")
        footer.addWidget(version)
        scroll.addLayout(footer)

        self.setCentralWidget(central)

    # ------------------------------------------------------------------
    # Tray
    # ------------------------------------------------------------------

    def _init_tray(self) -> None:
        self._tray = QSystemTrayIcon(build_app_icon(), self)
        self._tray.setToolTip(f"{APP_NAME} — disconnected")

        from PySide6.QtGui import QAction  # noqa: PLC0415 - local import fine

        self._show_action = QAction("Show / Hide window", self)
        self._show_action.triggered.connect(self.toggle_visibility)
        self._tray_start_action = QAction("Start AFK", self)
        self._tray_start_action.triggered.connect(self._on_start_clicked)
        self._tray_stop_action = QAction("Stop AFK", self)
        self._tray_stop_action.triggered.connect(self._on_stop_clicked)
        self._tray_stop_action.setEnabled(False)
        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(self._on_exit_action)

        from PySide6.QtWidgets import QMenu  # noqa: PLC0415

        menu = QMenu()
        menu.addAction(self._show_action)
        menu.addSeparator()
        menu.addAction(self._tray_start_action)
        menu.addAction(self._tray_stop_action)
        menu.addSeparator()
        menu.addAction(exit_action)
        self._tray.setContextMenu(menu)
        self._tray.activated.connect(self._on_tray_activated)
        self._tray.show()

    def _on_tray_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.DoubleClick:
            self.toggle_visibility()

    def toggle_visibility(self) -> None:
        """Show and raise the window, or hide it if already visible."""
        if self.isVisible() and not self.isMinimized():
            self.hide()
        else:
            self.showNormal()
            self.raise_()
            self.activateWindow()

    def focus_window(self) -> None:
        """Bring the window to the front (single-instance focus request)."""
        self.showNormal()
        self.raise_()
        self.activateWindow()

    # ------------------------------------------------------------------
    # Account actions
    # ------------------------------------------------------------------

    def _ensure_authenticator(self) -> MinecraftAuthenticator:
        if self._authenticator is None:
            self._authenticator = MinecraftAuthenticator(
                self._token_store, client_id=self._client_id
            )
        return self._authenticator

    def _on_login(self) -> None:
        if self._session_running():
            QMessageBox.information(
                self, "Stop AFK first",
                "Stop the AFK session before changing the account.",
            )
            return
        if not self._client_id:
            QMessageBox.warning(
                self, "Setup required",
                "No Azure application (client) ID is configured.\n\n"
                "One-time setup (free, ~5 minutes):\n"
                "1. Follow README → 'Setup: Azure app registration'.\n"
                "2. Set azure_client_id in config.toml or the "
                "ANTLANTISAFK_CLIENT_ID environment variable.\n\n"
                "This ID identifies the app to Microsoft's login servers and "
                "is not a secret.",
            )
            return

        self._set_account_status(AccountStatus.LOGGING_IN)
        dialog = LoginDialog(self._ensure_authenticator(), self)
        result = dialog.exec()
        if result == LoginDialog.Accepted and dialog.auth_result:
            self._auth_result = dialog.auth_result
            self._set_account_status(AccountStatus.LOGGED_IN)
            self._profile_changed.emit(dialog.auth_result.username)
            logger.info("Logged in as %s.", dialog.auth_result.username)
        else:
            self._set_account_status(
                AccountStatus.ERROR
                if self._auth_result is None
                else AccountStatus.LOGGED_IN
            )

    def _on_logout(self) -> None:
        if self._session_running():
            QMessageBox.information(
                self, "Stop AFK first",
                "Stop the AFK session before logging out.",
            )
            return
        confirm = QMessageBox.question(
            self, "Logout / Delete Credentials",
            "Delete the stored refresh token and log out?\n\n"
            "You will need to sign in again with Microsoft next time.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return
        try:
            self._ensure_authenticator().logout()
        except Exception as exc:  # noqa: BLE001 - user-visible
            logger.error("Logout failed: %s", exc)
            QMessageBox.warning(self, "Logout problem",
                                f"Could not fully delete credentials: {exc}")
        self._auth_result = None
        self._profile_changed.emit("")
        self._set_account_status(AccountStatus.NOT_LOGGED_IN)
        logger.info("Logged out; all stored credentials deleted.")

    def _set_account_status(self, status: AccountStatus) -> None:
        self._account_status = status
        self._account_changed.emit(status)

    def _on_account_changed(self, status: AccountStatus) -> None:
        self._account_pill.set_status(
            ACCOUNT_STATUS_TEXT[status], _ACCOUNT_PILL_COLOR[status]
        )
        logged_in = self._auth_result is not None
        self._login_btn.setEnabled(not logged_in and status != AccountStatus.LOGGING_IN)
        self._logout_btn.setEnabled(logged_in)
        self._refresh_action_buttons()

    def _on_profile_changed(self, username: str) -> None:
        self._username_label.setText(username or "—")

    # ------------------------------------------------------------------
    # Session control
    # ------------------------------------------------------------------

    def _collect_config(self) -> AppConfig | None:
        """Read GUI fields into a validated config (None on failure)."""
        cfg = AppConfig(
            server_address=self._server_edit.text(),
            server_port=self._port_spin.value(),
            minecraft_version=self._version_edit.text().strip() or "auto",
            reconnect_delay_seconds=self._delay_spin.value(),
            max_reconnect_attempts=self._retries_spin.value(),
            minimize_to_tray=self._tray_check.isChecked(),
            azure_client_id=self._client_id,
        )
        try:
            cfg.validate()
        except ConfigError as exc:
            QMessageBox.warning(self, "Invalid settings", str(exc))
            return None
        return cfg

    def _on_start_clicked(self) -> None:
        if self._session_running():
            return
        if self._auth_result is None:
            QMessageBox.information(
                self, "Not logged in",
                "Log in with Microsoft first (Account section).",
            )
            return

        cfg = self._collect_config()
        if cfg is None:
            return
        self._config = cfg
        try:
            self._config_manager.save(cfg)
        except ConfigError as exc:
            logger.error("Could not save configuration: %s", exc)

        if self._auth_result.token_expired():
            logger.info("Minecraft token expired; refreshing silently…")
            self._set_account_status(AccountStatus.LOGGING_IN)
            threading.Thread(target=self._refresh_then_start, daemon=True).start()
            return

        self._start_session(cfg)

    def _refresh_then_start(self) -> None:
        """Background: silently refresh credentials, then start the session."""
        try:
            refreshed = self._ensure_authenticator().restore_session()
        except TokenRefreshError as exc:
            logger.error("Silent refresh failed: %s", exc)
            self._auth_result = None
            self._account_changed.emit(AccountStatus.TOKEN_EXPIRED)
            return
        if refreshed is None:
            self._account_changed.emit(AccountStatus.TOKEN_EXPIRED)
            return
        self._auth_result = refreshed
        self._profile_changed.emit(refreshed.username)
        self._account_changed.emit(AccountStatus.LOGGED_IN)
        # AfkSession is thread-safe, so the background thread may start it
        # directly; state updates reach the GUI via the _session_changed signal.
        self._start_session(self._config)

    def _start_session(self, cfg: AppConfig) -> None:
        assert self._auth_result is not None
        if self._auth_result.token_expired():
            QMessageBox.warning(
                self, "Token expired",
                "The Minecraft token could not be refreshed. Please log in "
                "again with Microsoft.",
            )
            self._set_account_status(AccountStatus.TOKEN_EXPIRED)
            return
        self._session = AfkSession(
            cfg,
            self._auth_result,
            on_change=lambda snapshot: self._session_changed.emit(snapshot),
        )
        self._session.start()
        self._set_inputs_enabled(False)
        self._refresh_action_buttons()
        logger.info("AFK session starting for %s.", self._auth_result.username)

    def _on_stop_clicked(self) -> None:
        if self._session is not None:
            self._session.stop()
        self._refresh_action_buttons()

    def _session_running(self) -> bool:
        return self._session is not None and self._session.snapshot().state not in (
            SessionState.IDLE, SessionState.ERROR
        ) and self._session.snapshot().state != SessionState.STOPPING

    def _on_session_changed(self, snapshot: SessionSnapshot) -> None:
        from ..status import ConnectionStatus as _CS  # noqa: PLC0415

        mapping = {
            SessionState.IDLE: ConnectionStatus.DISCONNECTED,
            SessionState.CONNECTING: ConnectionStatus.CONNECTING,
            SessionState.CONNECTED: ConnectionStatus.CONNECTED,
            SessionState.WAITING_RETRY: ConnectionStatus.RECONNECTING,
            SessionState.STOPPING: ConnectionStatus.DISCONNECTED,
            SessionState.ERROR: ConnectionStatus.ERROR,
        }
        conn_status = mapping[snapshot.state]
        self._conn_pill.set_status(
            CONNECTION_STATUS_TEXT[conn_status], _CONN_PILL_COLOR[conn_status]
        )
        self._uptime_label.setText(self._format_uptime(snapshot.uptime_seconds))
        self._reconnects_label.setText(str(snapshot.reconnect_count))
        if snapshot.next_retry_at is not None:
            remaining = max(0, int(snapshot.next_retry_at - time.time()))
            self._retry_label.setText(f"in {remaining}s")
        else:
            self._retry_label.setText("—")
        if snapshot.last_error and snapshot.state == SessionState.ERROR:
            self._conn_pill.setToolTip(snapshot.last_error)
        self._tray.setToolTip(
            f"{APP_NAME} — {CONNECTION_STATUS_TEXT[conn_status]}"
        )
        self._refresh_action_buttons()

    def _on_session_stopped(self) -> None:
        self._session = None
        self._set_inputs_enabled(True)
        self._refresh_action_buttons()

    @staticmethod
    def _format_uptime(seconds: int) -> str:
        h, rem = divmod(max(0, seconds), 3600)
        m, s = divmod(rem, 60)
        return f"{h:02d}:{m:02d}:{s:02d}"

    # ------------------------------------------------------------------
    # Misc
    # ------------------------------------------------------------------

    def _tick(self) -> None:
        if self._session is not None:
            self._on_session_changed(self._session.snapshot())

    def _set_inputs_enabled(self, enabled: bool) -> None:
        for widget in (self._server_edit, self._port_spin, self._version_edit,
                       self._delay_spin, self._retries_spin):
            widget.setEnabled(enabled)

    def _refresh_action_buttons(self) -> None:
        running = self._session_running()
        logged_in = self._auth_result is not None
        self._start_btn.setEnabled(logged_in and not running)
        self._stop_btn.setEnabled(running)
        self._tray_start_action.setEnabled(logged_in and not running)
        self._tray_stop_action.setEnabled(running)
        self._login_btn.setEnabled(not logged_in and
                                   self._account_status != AccountStatus.LOGGING_IN)
        self._logout_btn.setEnabled(logged_in and not running)

    def _restore_session_silently(self) -> None:
        """Background: try to restore the previous login from the refresh token."""
        if not self._client_id:
            return

        def work() -> None:
            try:
                result = self._ensure_authenticator().restore_session()
            except TokenRefreshError as exc:
                logger.info("Stored session could not be renewed: %s", exc)
                self._account_changed.emit(AccountStatus.TOKEN_EXPIRED)
                return
            except Exception:  # noqa: BLE001
                logger.exception("Silent session restore failed.")
                return
            if result is not None:
                self._auth_result = result
                self._profile_changed.emit(result.username)
                self._account_changed.emit(AccountStatus.LOGGED_IN)
                logger.info("Session restored for %s.", result.username)

        threading.Thread(target=work, name="session-restore", daemon=True).start()

    def _on_exit_action(self) -> None:
        self._shutdown()
        QApplication.quit()

    def _shutdown(self) -> None:
        """Stop the session and hide the tray before the app exits."""
        if self._session is not None:
            try:
                self._session.stop()
            except Exception:  # noqa: BLE001
                logger.exception("Error stopping session during shutdown.")
            self._session = None
        try:
            self._tray.hide()
        except Exception:  # noqa: BLE001
            pass
        logger.info("%s shutting down.", APP_NAME)

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt override
        """Minimize to tray while connected, or shut down completely."""
        if self._config.minimize_to_tray and self._session_running():
            event.ignore()
            self.hide()
            self._tray.showMessage(
                APP_NAME,
                "AntlantisAFK keeps running in the tray.",
                QSystemTrayIcon.Information, 3000,
            )
            return
        self._shutdown()
        event.accept()
        super().closeEvent(event)
