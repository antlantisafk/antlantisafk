"""Tests for the AFK session reconnect logic (all networking faked)."""

from __future__ import annotations

import threading
import time
from typing import Any

import pytest

from antlantisafk.auth.manager import AuthResult
from antlantisafk.config import AppConfig
from antlantisafk.minecraft.session import AfkSession, SessionState


class FakeBridge:
    """Stands in for WorkerBridge: instantly failing connect attempts."""

    def __init__(self, fail_times: int | None = None) -> None:
        self.fail_times = fail_times  # None = always fail
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.started = False
        self.stopped = False
        self.handlers: dict[str, list] = {}
        self._connected_emitted = threading.Event()

    # --- bridge API used by AfkSession ---
    def start(self) -> None:
        self.started = True

    def stop(self, timeout: float = 5.0) -> None:
        self.stopped = True

    def is_running(self) -> bool:
        return self.started and not self.stopped

    def on(self, event: str, handler) -> None:
        self.handlers.setdefault(event, []).append(handler)

    def send_token_handshake(self, access_token: str, username: str,
                             uuid: str) -> dict[str, Any]:
        self.calls.append(("auth_handshake", {}))
        return {"ready": True}

    def request(self, cmd: str, args: dict[str, Any] | None = None,
                timeout: float = 90.0) -> dict[str, Any]:
        self.calls.append((cmd, args or {}))
        if cmd == "connect":
            if self.fail_times is None or self.fail_times > 0:
                if self.fail_times is not None:
                    self.fail_times -= 1
                raise RuntimeError("connection refused (fake)")
            return {"connecting": True}
        return {}

    def emit(self, event: str, data: dict[str, Any]) -> None:
        for handler in self.handlers.get(event, ()):
            handler(data)


def make_session(cfg: AppConfig | None = None,
                 bridge: FakeBridge | None = None) -> AfkSession:
    cfg = cfg or AppConfig(server_address="play.example.net")
    auth = AuthResult(
        username="TestPlayer",
        uuid="1234567890abcdef1234567890abcdef",
        access_token="fake-mc-access-token",  # fake — never a real credential
        expires_at=time.time() + 3600,
    )
    return AfkSession(cfg, auth, bridge=bridge or FakeBridge())


class TestBackoff:
    def test_backoff_doubles_and_caps(self):
        session = make_session()
        delays = [session._backoff_delay(a) for a in range(1, 9)]
        assert delays[0] == 5      # base
        assert delays[1] == 10
        assert delays[2] == 20
        assert delays[3] == 40
        assert delays[-1] == 600   # capped at 10 minutes

    def test_custom_base_delay(self):
        cfg = AppConfig(server_address="a.example.net",
                        reconnect_delay_seconds=3)
        session = make_session(cfg)
        assert session._backoff_delay(1) == 3
        assert session._backoff_delay(2) == 6
        assert session._backoff_delay(3) == 12


class TestReconnectFlow:
    def test_gives_up_after_max_attempts(self):
        cfg = AppConfig(server_address="a.example.net",
                        reconnect_delay_seconds=0,  # no waiting between tries
                        max_reconnect_attempts=3)
        bridge = FakeBridge()  # always fails
        session = make_session(cfg, bridge)
        session.start()
        deadline = time.time() + 5.0
        while time.time() < deadline:
            if session.snapshot().state == SessionState.ERROR:
                break
            time.sleep(0.01)
        snap = session.snapshot()
        assert snap.state == SessionState.ERROR
        # 3 attempts total = 1 initial connect + 2 reconnects.
        assert snap.attempt == 3
        assert snap.reconnect_count == 2
        assert "connection refused" in snap.last_error

    def test_succeeds_after_failures(self):
        cfg = AppConfig(server_address="a.example.net",
                        reconnect_delay_seconds=0, max_reconnect_attempts=10)
        bridge = FakeBridge(fail_times=2)  # fails twice, then succeeds
        session = make_session(cfg, bridge)
        session.start()
        deadline = time.time() + 5.0
        while time.time() < deadline:
            if session.snapshot().state == SessionState.CONNECTED:
                break
            time.sleep(0.01)
        assert session.snapshot().state == SessionState.CONNECTED
        connect_calls = [c for c in bridge.calls if c[0] == "connect"]
        assert len(connect_calls) == 3  # 2 failures + 1 success

    def test_stop_during_reconnect_loop(self):
        cfg = AppConfig(server_address="a.example.net",
                        reconnect_delay_seconds=0, max_reconnect_attempts=0)
        session = make_session(cfg, FakeBridge())
        session.start()
        time.sleep(0.1)
        session.stop()
        deadline = time.time() + 3.0
        while time.time() < deadline:
            if session.snapshot().state == SessionState.IDLE:
                break
            time.sleep(0.01)
        assert session.snapshot().state == SessionState.IDLE
        assert session._stop_requested.is_set()


class TestWorkerEvents:
    def test_worker_end_triggers_reconnect(self):
        bridge = FakeBridge(fail_times=0)  # reconnects succeed
        cfg = AppConfig(server_address="a.example.net",
                        reconnect_delay_seconds=0, max_reconnect_attempts=5)
        session = make_session(cfg, bridge)
        session.start()
        deadline = time.time() + 5.0
        while time.time() < deadline:
            if session.snapshot().state == SessionState.CONNECTED:
                break
            time.sleep(0.01)
        assert session.snapshot().state == SessionState.CONNECTED

        bridge.emit("end", {"reason": "Server closed"})
        deadline = time.time() + 5.0
        while time.time() < deadline:
            snap = session.snapshot()
            if snap.state == SessionState.CONNECTED and snap.reconnect_count == 1:
                break
            time.sleep(0.01)
        snap = session.snapshot()
        assert snap.state == SessionState.CONNECTED
        assert snap.reconnect_count == 1

    def test_worker_kicked_triggers_reconnect(self):
        bridge = FakeBridge(fail_times=0)  # reconnects succeed
        cfg = AppConfig(server_address="a.example.net",
                        reconnect_delay_seconds=0, max_reconnect_attempts=5)
        session = make_session(cfg, bridge)
        session.start()
        deadline = time.time() + 5.0
        while time.time() < deadline:
            if session.snapshot().state == SessionState.CONNECTED:
                break
            time.sleep(0.01)
        bridge.emit("kicked", {"reason": "Banned:AFK"})
        deadline = time.time() + 5.0
        while time.time() < deadline:
            snap = session.snapshot()
            if snap.reconnect_count == 1 and snap.state in (
                SessionState.CONNECTED, SessionState.ERROR, SessionState.WAITING_RETRY
            ):
                break
            time.sleep(0.01)
        assert session.snapshot().reconnect_count == 1


class TestPassivity:
    def test_session_never_sends_gameplay_commands(self):
        """The bridge API must never receive gameplay/automation commands."""
        bridge = FakeBridge(fail_times=0)
        session = make_session(AppConfig(server_address="a.example.net"), bridge)
        session.start()
        deadline = time.time() + 3.0
        while time.time() < deadline:
            if session.snapshot().state == SessionState.CONNECTED:
                break
            time.sleep(0.01)

        forbidden = {"move", "chat", "chat_spam", "swing", "use_item",
                     "interact", "mine", "attack", "command"}
        for cmd, _args in bridge.calls:
            assert cmd not in forbidden, f"Forbidden automation command: {cmd}"
