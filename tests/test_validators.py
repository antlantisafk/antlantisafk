"""Tests for antlantisafk.utils.validators."""

from __future__ import annotations

import pytest

from antlantisafk.utils.validators import (
    ValidationError,
    validate_minecraft_version,
    validate_nonempty,
    validate_port,
    validate_server_address,
)


class TestServerAddress:
    @pytest.mark.parametrize("addr", [
        "play.example.net",
        "mc.server.org",
        "localhost",
        "203.0.113.10",
        "hypixel.net",
        "play_myserver.net",  # underscores tolerated (common in MC community)
    ])
    def test_accepts_valid(self, addr):
        assert validate_server_address(addr) == addr.lower()

    def test_accepts_ipv6_bracketed(self):
        assert validate_server_address("[::1]") == "[::1]"
        assert validate_server_address("[2001:db8::1]") == "[2001:db8::1]"

    def test_accepts_bare_ipv6(self):
        assert validate_server_address("::1") == "::1"

    def test_strips_whitespace_and_lowercases(self):
        assert validate_server_address("  Play.Example.NET ") == "play.example.net"

    @pytest.mark.parametrize("addr", [
        "", "   ",
        "not a host",
        "-bad.example.com",       # leading hyphen
        "bad.example.com-",       # trailing hyphen
        "play..example.net",      # empty label
        "play example net",       # spaces
        "[notanip]",              # brackets without valid IPv6
        "x" * 300,                # absurdly long
        "play.example.net.",      # trailing dot
    ])
    def test_rejects_invalid(self, addr):
        with pytest.raises(ValidationError):
            validate_server_address(addr)


class TestPort:
    @pytest.mark.parametrize("port", [1, 25565, 65535, "25565", " 8123 "])
    def test_accepts_valid(self, port):
        assert validate_port(port) == int(port)

    @pytest.mark.parametrize("port", [0, -1, 65536, "abc", "", None])
    def test_rejects_invalid(self, port):
        with pytest.raises(ValidationError):
            validate_port(port)


class TestMinecraftVersion:
    @pytest.mark.parametrize("version", ["auto", "AUTO", "1.20", "1.20.4", "1.21.1"])
    def test_accepts_valid(self, version):
        assert validate_minecraft_version(version) == version.lower()

    @pytest.mark.parametrize("version", ["", "one.twenty", "1", "1.20.4.1",
                                         "v1.20", "1.200"])
    def test_rejects_invalid(self, version):
        with pytest.raises(ValidationError):
            validate_minecraft_version(version)


class TestNonEmpty:
    def test_accepts(self):
        assert validate_nonempty("field", "  hello  ") == "hello"

    def test_rejects_empty(self):
        with pytest.raises(ValidationError):
            validate_nonempty("field", "   ")

    def test_rejects_too_long(self):
        with pytest.raises(ValidationError):
            validate_nonempty("field", "x" * 5000, max_len=100)
