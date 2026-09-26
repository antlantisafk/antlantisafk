"""Single-instance enforcement for AntlantisAFK.

On Windows a named mutex guarantees only one running instance. When a second
instance starts it asks the first (via a tiny local TCP hello on a fixed
loopback port) to raise its window, then exits. On non-Windows platforms a
lock file is used instead.

The socket only listens on 127.0.0.1 and accepts one command ("focus"),
carrying no data payload beyond the command word — it is not a general
remote-control interface.
"""

from __future__ import annotations

import hashlib
import logging
import os
import socket
import sys
from pathlib import Path

from .. import APP_NAME
from ..constants import FOCUS_PORT_BASE, SINGLE_INSTANCE_MUTEX, appdata_dir

logger = logging.getLogger(__name__)

_FOCUS_COMMAND: bytes = b"ANTLANTIS_FOCUS\n"
_FOCUS_ACK: bytes = b"ANTLANTIS_OK\n"


class SingleInstance:
    """Cross-platform single-instance guard.

    Usage::

        guard = SingleInstance()
        if not guard.acquire():
            guard.ask_running_instance_to_focus()
            sys.exit(0)
        try:
            ... run app ...
        finally:
            guard.release()
    """

    def __init__(self) -> None:
        self._mutex_handle: object | None = None
        self._lock_file: Path | None = None
        self._listener: socket.socket | None = None
        self._port: int = self._derive_port()

    # -- helpers -------------------------------------------------------------

    @staticmethod
    def _fingerprint() -> str:
        """Stable short fingerprint so different users don't collide."""
        user = os.environ.get("USERNAME") or os.environ.get("USER") or "user"
        return hashlib.sha1(f"{APP_NAME}:{user}".encode()).hexdigest()[:10]

    def _derive_port(self) -> int:
        fp = self._fingerprint()
        return FOCUS_PORT_BASE + (int(fp, 16) % 500)

    # -- acquisition ---------------------------------------------------------

    def acquire(self) -> bool:
        """Try to become the single running instance. True on success."""
        if sys.platform.startswith("win"):
            return self._acquire_windows_mutex()
        return self._acquire_lock_file()

    def _acquire_windows_mutex(self) -> bool:
        try:
            import win32api  # type: ignore[import-untyped]
            import win32event  # type: ignore[import-untyped]
            import winerror  # type: ignore[import-untyped]

            name = SINGLE_INSTANCE_MUTEX.format(fingerprint=self._fingerprint())
            handle = win32event.CreateMutex(None, False, name)
            if winerror.ERROR_ALREADY_EXISTS == win32api.GetLastError():
                handle.Close()
                logger.info("Another %s instance is already running.", APP_NAME)
                return False
            self._mutex_handle = handle
            logger.debug("Acquired single-instance mutex '%s'.", name)
            return True
        except ImportError:
            # Non-Windows or pywin32 missing: fall back to lock file.
            logger.debug("win32 modules unavailable; using lock-file guard.")
            return self._acquire_lock_file()

    def _acquire_lock_file(self) -> bool:
        lock = appdata_dir() / "antlantisafk.lock"
        try:
            # O_EXCL guarantees atomic create-if-not-exists.
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            self._lock_file = lock
            logger.debug("Acquired lock file %s.", lock)
            return True
        except FileExistsError:
            logger.info("Lock file %s exists; another instance is running.", lock)
            return False
        except OSError as exc:
            logger.warning("Could not create lock file %s: %s", lock, exc)
            # Fail open rather than blocking the user entirely.
            return True

    # -- focus notification --------------------------------------------------

    def ask_running_instance_to_focus(self) -> bool:
        """Ask the already-running instance to show/focus its window."""
        try:
            with socket.create_connection(("127.0.0.1", self._port), timeout=2.0) as sock:
                sock.sendall(_FOCUS_COMMAND)
                data = sock.recv(len(_FOCUS_ACK))
                return data.startswith(b"ANTLANTIS_OK")
        except OSError as exc:
            logger.debug("Focus handshake failed: %s", exc)
            return False

    def start_focus_listener(self, on_focus) -> None:
        """Start a loopback listener that calls ``on_focus()`` when pinged."""
        self._on_focus = on_focus
        try:
            srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            srv.bind(("127.0.0.1", self._port))
            srv.listen(2)
            srv.settimeout(1.0)
            self._listener = srv
        except OSError as exc:
            logger.warning("Focus listener unavailable on port %s: %s", self._port, exc)
            return

        import threading

        def _serve() -> None:
            while self._listener is not None:
                try:
                    conn, addr = self._listener.accept()
                except socket.timeout:
                    continue
                except OSError:
                    break
                with conn:
                    try:
                        conn.settimeout(2.0)
                        data = conn.recv(64)
                        if data.startswith(_FOCUS_COMMAND.strip()):
                            conn.sendall(_FOCUS_ACK)
                            callback = self._on_focus
                            if callback is not None:
                                try:
                                    callback()
                                except Exception:  # noqa: BLE001
                                    logger.exception("Focus callback failed.")
                    except OSError:
                        continue

        threading.Thread(target=_serve, name="focus-listener", daemon=True).start()
        logger.debug("Focus listener listening on 127.0.0.1:%s", self._port)

    # -- release -------------------------------------------------------------

    def release(self) -> None:
        """Release all single-instance resources."""
        if self._listener is not None:
            try:
                self._listener.close()
            except OSError:
                pass
            self._listener = None
        if self._mutex_handle is not None:
            try:
                self._mutex_handle.Close()  # type: ignore[attr-defined]
            except Exception:  # noqa: BLE001
                pass
            self._mutex_handle = None
        if self._lock_file is not None:
            try:
                self._lock_file.unlink(missing_ok=True)
            except OSError:
                pass
            self._lock_file = None
