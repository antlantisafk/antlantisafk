"""Tests for antlantisafk.security.token_store.

The tests use an in-memory fake to verify the *abstraction* and call sites;
backend-specific tests skip automatically when keyring/DPAPI backends are
unavailable (e.g. CI without a credential service). No real credentials are
ever used.
"""

from __future__ import annotations

import pytest

from antlantisafk.security.token_store import (
    DPAPITokenStore,
    KeyringTokenStore,
    TokenStore,
    TokenStoreError,
    create_token_store,
)


class InMemoryTokenStore(TokenStore):
    """Test double: verifies the abstraction without touching the OS."""

    def __init__(self) -> None:
        self.saved: dict[str, str] = {}
        self.deleted = 0

    def save_refresh_token(self, token: str) -> None:
        self.saved["refresh"] = token

    def load_refresh_token(self) -> str | None:
        return self.saved.get("refresh")

    def delete_credentials(self) -> None:
        self.saved.clear()
        self.deleted += 1


class TestAbstraction:
    def test_save_load_round_trip(self):
        store = InMemoryTokenStore()
        store.save_refresh_token("fake-token-value")
        assert store.load_refresh_token() == "fake-token-value"

    def test_delete_clears(self):
        store = InMemoryTokenStore()
        store.save_refresh_token("fake-token-value")
        store.delete_credentials()
        assert store.load_refresh_token() is None
        assert store.deleted == 1

    def test_load_absent_returns_none(self):
        assert InMemoryTokenStore().load_refresh_token() is None

    def test_authenticator_uses_abstract_store(self, isolated_appdata):
        """The auth layer must work with any TokenStore implementation."""
        from antlantisafk.auth.manager import MinecraftAuthenticator

        store = InMemoryTokenStore()
        auth = MinecraftAuthenticator(store, client_id="test-client-id")
        # logout() must clear the store even without a prior login.
        auth.logout()
        assert store.deleted == 1


class TestBackends:
    def test_create_store_returns_something(self, isolated_appdata):
        """On a normal dev machine one of the backends must be creatable."""
        try:
            store = create_token_store()
        except TokenStoreError as exc:
            pytest.skip(f"No secure token backend available here: {exc}")
        assert isinstance(store, (KeyringTokenStore, DPAPITokenStore))

    def test_keyring_round_trip_if_available(self, isolated_appdata):
        try:
            store = KeyringTokenStore()
        except TokenStoreError:
            pytest.skip("keyring backend unavailable")
        try:
            store.save_refresh_token("antlantis-test-token")
            assert store.load_refresh_token() == "antlantis-test-token"
        finally:
            store.delete_credentials()

    def test_dpapi_round_trip_if_available(self, isolated_appdata):
        if not DPAPITokenStore.__module__.startswith("antlantisafk"):
            pytest.skip("unreachable")
        try:
            store = DPAPITokenStore()
        except TokenStoreError:
            pytest.skip("pywin32/DPAPI unavailable")
        try:
            store.save_refresh_token("antlantis-test-token")
            assert store.load_refresh_token() == "antlantis-test-token"
            store.delete_credentials()
            assert store.load_refresh_token() is None
        finally:
            store.delete_credentials()
