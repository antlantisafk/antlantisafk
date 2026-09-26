"""Rotating-file logging setup for AntlantisAFK.

File log captures DEBUG and above; the GUI log area displays INFO and above by
default. Tokens, session IDs, and passwords are never logged — auth modules
must use :data:`REDACTED` placeholders for any secret value.
"""

from __future__ import annotations

import logging
import logging.handlers
import os
import sys

from . import APP_NAME
from .constants import LOG_BACKUP_COUNT, LOG_FORMAT, LOG_MAX_BYTES, log_file_path

#: Placeholder used wherever a secret would otherwise appear in a log line.
REDACTED: str = "[REDACTED]"


def setup_logging(verbose: bool = False) -> logging.RootLogger:
    """Configure the root logger with a rotating file handler.

    Args:
        verbose: If True, log DEBUG to file; otherwise INFO.

    Returns:
        The configured root logger.
    """
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    # Avoid duplicate handlers if setup_logging is called twice.
    for handler in list(root.handlers):
        root.removeHandler(handler)

    log_path = log_file_path()
    try:
        handler = logging.handlers.RotatingFileHandler(
            log_path,
            maxBytes=LOG_MAX_BYTES,
            backupCount=LOG_BACKUP_COUNT,
            encoding="utf-8",
        )
    except OSError:
        # Fallback: log to stderr if the appdata dir is unwritable.
        handler = logging.StreamHandler(sys.stderr)
        root.error("Could not open log file %s; logging to stderr.", log_path)

    handler.setLevel(logging.DEBUG if verbose else logging.INFO)
    handler.setFormatter(logging.Formatter(LOG_FORMAT))
    root.addHandler(handler)

    # Quiet noisy third-party loggers unless debugging.
    logging.getLogger("urllib3").setLevel(logging.WARNING if not verbose else logging.DEBUG)
    logging.getLogger("msal").setLevel(logging.INFO if not verbose else logging.DEBUG)

    logging.getLogger(__name__).debug(
        "%s logging initialised (file=%s, max_bytes=%s, backups=%s).",
        APP_NAME, log_path, LOG_MAX_BYTES, LOG_BACKUP_COUNT,
    )
    return root


def log_exception(logger: logging.Logger, message: str, exc: BaseException) -> None:
    """Log a message with full traceback; never raise from logging."""
    try:
        logger.exception("%s: %s", message, exc)
    except OSError:
        # Disk full etc. — swallow so an error never crashes the app.
        os.stderr = sys.stderr  # noqa: F841  (keep linters quiet)
        print(f"Logging failed: {exc}", file=sys.stderr)
