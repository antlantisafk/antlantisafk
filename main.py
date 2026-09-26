"""AntlantisAFK entry point.

Wires together: logging, single-instance guard, configuration, secure token
storage, and the PySide6 GUI. Run with ``py -3 main.py`` from this folder
(see README for .exe build instructions).

This application intentionally provides NO way to enter raw session IDs or
third-party tokens, and NEVER asks for a Microsoft password. Authentication
happens exclusively through the official Microsoft device-code flow.
"""

from __future__ import annotations

import logging
import os
import sys
import traceback

from antlantisafk import APP_NAME, APP_VERSION
from antlantisafk.constants import DEFAULT_AZURE_CLIENT_ID, is_windows


def _fatal(exc: BaseException) -> None:
    """Log an unhandled exception with traceback, then exit non-zero."""
    logger = logging.getLogger(APP_NAME)
    logger.critical("Unhandled exception:\n%s",
                    "".join(traceback.format_exception(exc)))


def main() -> int:
    # Logging first so every later step is captured.
    from antlantisafk.logging_setup import setup_logging

    setup_logging(verbose=bool(os.environ.get("ANTLANTISAFK_DEBUG")))
    logger = logging.getLogger(APP_NAME)
    logger.info("%s v%s starting (python %s).", APP_NAME, APP_VERSION,
                sys.version.split()[0])

    # Fail fast with a clear message on unsupported platforms.
    if not is_windows():
        logger.warning(
            "AntlantisAFK targets Windows 10/11; secure token storage and "
            "single-instance behaviour may be limited on this platform."
        )

    # Single instance: if another copy is running, ask it to focus and exit.
    from antlantisafk.security.single_instance import SingleInstance

    guard = SingleInstance()
    if not guard.acquire():
        logger.info("Focus request sent to the running instance; exiting.")
        guard.ask_running_instance_to_focus()
        return 0

    try:
        from PySide6.QtWidgets import QApplication

        from antlantisafk.config import ConfigManager
        from antlantisafk.gui.main_window import MainWindow
        from antlantisafk.gui.theme import apply_theme
        from antlantisafk.security.token_store import create_token_store

        config_manager = ConfigManager()
        config = config_manager.load()
        token_store = create_token_store()

        # Azure client id: environment variable, then config file, then the
        # built-in default. (The client ID is not a secret.)
        client_id = (
            os.environ.get("ANTLANTISAFK_CLIENT_ID", "").strip()
            or config.azure_client_id
            or DEFAULT_AZURE_CLIENT_ID
        )

        app = QApplication(sys.argv)
        app.setApplicationName(APP_NAME)
        app.setApplicationVersion(APP_VERSION)
        app.setQuitOnLastWindowClosed(False)  # tray keeps the app alive
        apply_theme(app)

        window = MainWindow(config, config_manager, token_store,
                            client_id=client_id)
        # Second launches ping this listener to raise the existing window.
        guard.start_focus_listener(on_focus=window.focus_window)

        window.show()
        exit_code = app.exec()

        guard.release()
        logger.info("%s exited normally (code %s).", APP_NAME, exit_code)
        return exit_code
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 - final safety net
        _fatal(exc)
        # Also surface a visible dialog when possible (GUI context).
        try:
            from PySide6.QtWidgets import QApplication, QMessageBox

            if QApplication.instance() is not None:
                QMessageBox.critical(
                    None, f"{APP_NAME} — fatal error",
                    f"An unexpected error occurred and the app must close.\n\n"
                    f"{exc}\n\nDetails were written to the log file.",
                )
        except Exception:  # noqa: BLE001
            pass
        return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
