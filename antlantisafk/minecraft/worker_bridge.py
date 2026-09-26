"""Subprocess bridge between Python and the Node.js mineflayer worker.

Protocol (newline-delimited JSON over the worker's stdin/stdout):

Python → worker (requests)::
    {"id": 1, "cmd": "connect", "args": {...}}
    {"id": 2, "cmd": "disconnect", "args": {}}
    {"id": 3, "cmd": "ping_worker", "args": {}}

Worker → Python (responses and events)::
    {"type": "response", "id": 1, "ok": true, "data": {...}}
    {"type": "response", "id": 1, "ok": false, "error": "human text"}
    {"type": "event", "event": "connected", "data": {...}}
    {"type": "log", "level": "info", "message": "..."}

Security notes:
- The worker receives the Minecraft access token via a **stdin handshake**
  (never command-line arguments, which are visible in process listings).
- The token is never logged by either side.
- The worker is strictly passive in-game: it answers keep-alives only.
"""

from __future__ import annotations

import json
import logging
import os
import queue
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Callable

from .exceptions import WorkerNotFoundError, WorkerStartupError

logger = logging.getLogger(__name__)

#: Extra seconds on top of the worker's own timeout before Python gives up.
REQUEST_TIMEOUT: float = 90.0

#: Executable names probed for the Node.js runtime.
_NODE_CANDIDATES: tuple[str, ...] = ("node.exe", "node", "nodejs")


class WorkerBridge:
    """Manage the worker process and exchange JSON lines with it.

    The bridge is transport-only: it knows nothing about Minecraft. Higher
    layers (:class:`antlantisafk.minecraft.session.AfkSession`) interpret
    worker events and implement reconnection policy.
    """

    def __init__(self, worker_script: Path | None = None) -> None:
        self._proc: subprocess.Popen[bytes] | None = None
        self._reader: threading.Thread | None = None
        self._pending: dict[int, queue.Queue[dict[str, Any]]] = {}
        self._pending_lock = threading.Lock()
        self._next_id = 1
        self._id_lock = threading.Lock()
        self._event_handlers: dict[str, list[Callable[[dict[str, Any]], None]]] = {}
        self._handlers_lock = threading.Lock()
        self._closed = threading.Event()
        self._worker_script = worker_script or self._default_worker_script()

    # -- paths / runtime discovery -------------------------------------------

    @staticmethod
    def _default_worker_script() -> Path:
        """Locate ``afk_worker.js`` (source tree, frozen bundle, or override)."""
        import sys

        override = (os.environ.get("ATLANTISAFK_WORKER")
                    or os.environ.get("ANTLANTISAFK_WORKER"))  # legacy alias
        if override and Path(override).exists():
            return Path(override)
        if getattr(sys, "frozen", False):
            base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
            for candidate in (
                base / "runtime" / "afk_worker.js",
                base / "antlantisafk" / "minecraft" / "worker" / "afk_worker.js",
            ):
                if candidate.exists():
                    return candidate
        return Path(__file__).resolve().parent / "worker" / "afk_worker.js"

    def find_node(self) -> str:
        """Return the path to a Node.js runtime.

        Order: ``ANTLANTISAFK_NODE`` env var, the bundled runtime inside a
        frozen exe (``runtime/node.exe``), a ``node.exe`` beside the worker
        script, then the system PATH.

        Raises:
            WorkerNotFoundError: No Node.js runtime could be located.
        """
        import sys

        custom = (os.environ.get("ATLANTISAFK_NODE")
                  or os.environ.get("ANTLANTISAFK_NODE"))  # legacy alias
        if custom and Path(custom).exists():
            return custom
        if getattr(sys, "frozen", False):
            base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
            bundled = base / "runtime" / "node.exe"
            if bundled.exists():
                return str(bundled)
        beside_worker = self._worker_script.parent / "node.exe"
        if beside_worker.exists():
            return str(beside_worker)
        for candidate in _NODE_CANDIDATES:
            path = shutil.which(candidate)
            if path:
                return path
        raise WorkerNotFoundError(
            "Node.js was not found. This build should include a bundled "
            "runtime; if it does not, install the LTS version from "
            "https://nodejs.org/ and run 'npm install minecraft-protocol' "
            "in the app's worker folder. See README 'Troubleshooting'."
        )

    def ensure_worker_dependencies(self) -> None:
        """Verify the worker script exists (deps checked at worker runtime)."""
        if not self._worker_script.exists():
            raise WorkerNotFoundError(
                f"Worker script not found at {self._worker_script}. The "
                "installation appears to be incomplete — reinstall the app."
            )

    # -- lifecycle ------------------------------------------------------------

    def start(self) -> None:
        """Spawn the worker process and start its stdout reader thread.

        Raises:
            WorkerNotFoundError: Node.js or the worker script is missing.
            WorkerStartupError: The process died immediately.
        """
        if self._proc is not None and self._proc.poll() is None:
            return  # already running
        self._closed.clear()
        self.ensure_worker_dependencies()
        node = self.find_node()

        creationflags = 0
        if os.name == "nt":  # pragma: no cover - Windows only flag
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

        try:
            self._proc = subprocess.Popen(  # noqa: S603 - fixed argv, no shell
                [node, str(self._worker_script)],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=str(self._worker_script.parent),
                creationflags=creationflags,
            )
        except OSError as exc:
            raise WorkerStartupError(f"Could not start Node.js worker: {exc}") from exc

        if self._proc.stdout is None or self._proc.stdin is None:
            self.stop()
            raise WorkerStartupError("Worker process pipes unavailable.")

        self._reader = threading.Thread(
            target=self._read_loop, name="worker-reader", daemon=True
        )
        self._reader.start()
        logger.info("Worker started (pid=%s, node=%s).", self._proc.pid, node)

        # Fail fast if the worker died on startup (e.g. missing npm module).
        time.sleep(0.4)
        if self._proc.poll() is not None:
            stderr = self._read_stderr()
            raise WorkerStartupError(
                f"Worker exited immediately (code {self._proc.returncode}). "
                f"{stderr}"
            )

    def stop(self, timeout: float = 5.0) -> None:
        """Terminate the worker gracefully and release all resources."""
        self._closed.set()
        proc = self._proc
        self._proc = None
        if proc is None:
            return
        if proc.poll() is None:
            self._send_raw({"type": "shutdown"})
            try:
                proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                logger.warning("Worker did not exit in %.1fs; terminating.", timeout)
                proc.terminate()
                try:
                    proc.wait(timeout=3.0)
                except subprocess.TimeoutExpired:
                    proc.kill()
        # Wake any pending request waiters so they do not hang forever.
        with self._pending_lock:
            for q in self._pending.values():
                q.put({"type": "response", "ok": False,
                       "error": "worker stopped"})
            self._pending.clear()
        logger.info("Worker stopped.")

    def is_running(self) -> bool:
        """True while the worker process is alive."""
        return self._proc is not None and self._proc.poll() is None

    # -- requests -------------------------------------------------------------

    def request(self, cmd: str, args: dict[str, Any] | None = None,
                timeout: float = REQUEST_TIMEOUT) -> dict[str, Any]:
        """Send a command and wait for its response.

        Args:
            cmd: Command name (``connect``, ``disconnect``, ``ping_worker``).
            args: Command arguments.
            timeout: Seconds to wait for the response.

        Returns:
            The ``data`` payload from the worker.

        Raises:
            WorkerStartupError: The worker is not running or died.
            RuntimeError: The worker returned an error for this command.
            TimeoutError: No response arrived in time.
        """
        if not self.is_running():
            raise WorkerStartupError("Worker process is not running.")
        with self._id_lock:
            req_id = self._next_id
            self._next_id += 1
        q: queue.Queue[dict[str, Any]] = queue.Queue()
        with self._pending_lock:
            self._pending[req_id] = q
        try:
            self._send_raw({"id": req_id, "cmd": cmd, "args": args or {}})
            try:
                msg = q.get(timeout=timeout)
            except queue.Empty as exc:
                raise TimeoutError(f"Worker did not answer '{cmd}' in time.") from exc
            if not msg.get("ok", False):
                raise RuntimeError(str(msg.get("error", "unknown worker error")))
            return msg.get("data") or {}
        finally:
            with self._pending_lock:
                self._pending.pop(req_id, None)

    # -- events ---------------------------------------------------------------

    def on(self, event: str, handler: Callable[[dict[str, Any]], None]) -> None:
        """Register a handler for a worker event (``connected``, ``end``, …)."""
        with self._handlers_lock:
            self._event_handlers.setdefault(event, []).append(handler)

    # -- internals ------------------------------------------------------------

    def _send_raw(self, obj: dict[str, Any]) -> None:
        """Write one JSON line to the worker's stdin."""
        if self._proc is None or self._proc.stdin is None:
            raise WorkerStartupError("Worker stdin unavailable.")
        try:
            line = json.dumps(obj, separators=(",", ":")) + "\n"
            self._proc.stdin.write(line.encode("utf-8"))
            self._proc.stdin.flush()
        except (OSError, ValueError) as exc:
            raise WorkerStartupError(f"Lost contact with worker: {exc}") from exc

    def _read_loop(self) -> None:
        """Continuously parse worker stdout, dispatching responses/events."""
        proc = self._proc
        if proc is None or proc.stdout is None:
            return
        for raw in iter(proc.stdout.readline, b""):
            if self._closed.is_set():
                break
            line = raw.decode("utf-8", errors="replace").strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                logger.debug("Worker sent non-JSON line (ignored).")
                continue
            mtype = msg.get("type")
            if mtype == "response":
                self._resolve_pending(int(msg.get("id", -1)), msg)
            elif mtype == "event":
                self._dispatch_event(str(msg.get("event", "")), msg.get("data") or {})
            elif mtype == "log":
                level = str(msg.get("level", "info")).lower()
                message = str(msg.get("message", ""))
                # Worker logs are pre-sanitised; never log raw errors at info.
                logger.log(
                    logging.getLevelName(level.upper())
                    if level.upper() in ("DEBUG", "INFO", "WARNING", "ERROR")
                    else logging.INFO,
                    "[worker] %s", message,
                )
        logger.debug("Worker stdout reader exiting.")

    def _resolve_pending(self, req_id: int, msg: dict[str, Any]) -> None:
        with self._pending_lock:
            q = self._pending.get(req_id)
        if q is not None:
            q.put(msg)

    def _dispatch_event(self, event: str, data: dict[str, Any]) -> None:
        with self._handlers_lock:
            handlers = list(self._event_handlers.get(event, ()))
        for handler in handlers:
            try:
                handler(data)
            except Exception:  # noqa: BLE001 - handler errors must not kill us
                logger.exception("Event handler for '%s' raised.", event)

    def _read_stderr(self, limit: int = 800) -> str:
        """Best-effort read of buffered worker stderr for diagnostics."""
        proc = self._proc
        if proc is None or proc.stderr is None:
            return ""
        try:
            import fcntl  # POSIX only; Windows relies on the small buffer
            fd = proc.stderr.fileno()
            fcntl.fcntl(fd, fcntl.F_SETFL, os.O_NONBLOCK)  # type: ignore[arg-type]
            data = proc.stderr.read(limit) or b""
        except (ImportError, OSError, ValueError):
            data = b""
        return (data.decode("utf-8", errors="replace") if data else "").strip()

    # -- token handshake ------------------------------------------------------

    def send_token_handshake(self, access_token: str, username: str,
                             uuid: str) -> dict[str, Any]:
        """Hand the Minecraft access token to the worker over stdin.

        The token travels only through the pipe (never argv, never disk,
        never logs). The worker replies with a ``ready`` response.
        """
        return self.request(
            "auth_handshake",
            {"accessToken": access_token, "username": username, "uuid": uuid},
        )
