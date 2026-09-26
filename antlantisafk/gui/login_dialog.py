"""Modal Microsoft device-code login dialog.

Runs :meth:`MinecraftAuthenticator.start_device_login` on a background
QThread while showing the verification URL and user code. The dialog never
handles passwords — the user completes login in their browser.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QObject, Qt, QThread, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .. import APP_NAME
from ..auth.manager import AuthEvent, AuthResult, MinecraftAuthenticator
from .theme import COLORS

logger = logging.getLogger(__name__)


class _LoginWorker(QObject):
    """Runs the blocking device-code flow off the GUI thread."""

    device_code = Signal(str, str, int)  # url, code, expires_in
    progress = Signal(str)
    success = Signal(object)  # AuthResult
    failed = Signal(str)

    def __init__(self, authenticator: MinecraftAuthenticator) -> None:
        super().__init__()
        self._auth = authenticator

    def run(self) -> None:  # pragma: no cover - thread entry point
        def on_event(event: AuthEvent) -> None:
            if event.stage == "device_code" and event.verification_url:
                self.device_code.emit(
                    event.verification_url,
                    event.user_code or "",
                    event.expires_in or 900,
                )
            elif event.message:
                self.progress.emit(event.message)

        try:
            result = self._auth.start_device_login(on_event=on_event)
            self.success.emit(result)
        except Exception as exc:  # noqa: BLE001 - surfaced in the dialog
            logger.exception("Device login failed.")
            self.failed.emit(str(exc))


class LoginDialog(QDialog):
    """Interactive device-code login dialog.

    On success, :attr:`auth_result` holds the fresh :class:`AuthResult`.
    """

    def __init__(self, authenticator: MinecraftAuthenticator,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Sign in to {APP_NAME}")
        self.setModal(True)
        self.setMinimumWidth(460)
        self.auth_result: AuthResult | None = None

        self._thread: QThread | None = None
        self._worker: _LoginWorker | None = None
        self._authenticator = authenticator
        self._cancelled = False

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        title = QLabel("Sign in with Microsoft")
        title.setObjectName("Title")
        layout.addWidget(title)

        info = QLabel(
            "A code and link will appear below. Open the link in your "
            "browser, enter the code, and sign in with YOUR Microsoft "
            "account that owns Minecraft: Java Edition.\n\n"
            "AntlantisAFK never sees your password and never accepts "
            "session IDs or tokens from third parties."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        self._code_row = QWidget()
        code_layout = QHBoxLayout(self._code_row)
        code_layout.setContentsMargins(0, 0, 0, 0)
        self._code_label = QLabel("———")
        big = QFont()
        big.setPointSize(16)
        big.setBold(True)
        big.setLetterSpacing(QFont.PercentageSpacing, 115)
        self._code_label.setFont(big)
        self._code_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self._copy_btn = QPushButton("Copy code")
        self._copy_btn.clicked.connect(self._copy_code)
        self._open_btn = QPushButton("Open link")
        self._open_btn.clicked.connect(self._open_link)
        code_layout.addWidget(self._code_label, 1)
        code_layout.addWidget(self._copy_btn)
        code_layout.addWidget(self._open_btn)
        self._code_row.setVisible(False)
        layout.addWidget(self._code_row)

        self._url_label = QLabel("")
        self._url_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self._url_label.setVisible(False)
        layout.addWidget(self._url_label)

        self._status = QLabel("Starting device login…")
        self._status.setWordWrap(True)
        self._status.setStyleSheet(f"color: {COLORS['muted']};")
        layout.addWidget(self._status)

        self._progress = QProgressBar()
        self._progress.setRange(0, 0)  # indeterminate
        layout.addWidget(self._progress)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.clicked.connect(self.reject)
        buttons.addWidget(self._cancel_btn)
        layout.addLayout(buttons)

        self._start_login()

    # -- flow ----------------------------------------------------------------

    def _start_login(self) -> None:
        self._thread = QThread(self)
        self._worker = _LoginWorker(self._authenticator)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.device_code.connect(self._on_device_code)
        self._worker.progress.connect(self._on_progress)
        self._worker.success.connect(self._on_success)
        self._worker.failed.connect(self._on_failed)
        self._thread.start()

    # -- slots ---------------------------------------------------------------

    def _on_device_code(self, url: str, code: str, _expires_in: int) -> None:
        self._code_row.setVisible(True)
        self._url_label.setVisible(True)
        self._code_label.setText(code)
        self._url_label.setText(f"<a href='{url}'>{url}</a>")
        self._url_label.setOpenExternalLinks(True)
        self._status.setText("Waiting for you to complete sign-in in the browser…")

    def _on_progress(self, message: str) -> None:
        self._status.setText(message)

    def _on_success(self, result: object) -> None:
        if self._cancelled:
            return
        self.auth_result = result  # type: ignore[assignment]
        self._progress.hide()
        self.accept()

    def _on_failed(self, message: str) -> None:
        if self._cancelled:
            return
        self._progress.hide()
        self._status.setText(f"Login failed: {message}")
        self._status.setStyleSheet(f"color: {COLORS['danger']};")
        QMessageBox.critical(self, "Login failed", message)
        self.reject()

    def _copy_code(self) -> None:
        from PySide6.QtWidgets import QApplication

        QApplication.clipboard().setText(self._code_label.text())
        self._copy_btn.setText("Copied!")

    def _open_link(self) -> None:
        from PySide6.QtGui import QDesktopServices
        from PySide6.QtCore import QUrl

        if self._url_label.text():
            QDesktopServices.openUrl(QUrl(self._url_label.text().split("'")[1]))

    # -- cleanup ---------------------------------------------------------------

    def reject(self) -> None:  # noqa: D102 - QDialog override
        # The MSAL poll cannot be interrupted mid-call; ask the thread's
        # event loop to stop once the current run() returns. Late signals
        # are ignored via the cancelled flag (Qt auto-disconnects on
        # destruction).
        self._cancelled = True
        if self._thread is not None and self._thread.isRunning():
            try:
                self._thread.quit()
            except RuntimeError:
                pass
        super().reject()
