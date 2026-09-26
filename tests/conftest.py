"""Shared pytest fixtures for AntlantisAFK tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Make the project root (folder containing antlantisafk/) importable.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture()
def isolated_appdata(tmp_path, monkeypatch):
    """Point %APPDATA% at a temp dir so tests never touch real user data."""
    fake_appdata = tmp_path / "appdata"
    fake_appdata.mkdir()
    monkeypatch.setenv("APPDATA", str(fake_appdata))
    return fake_appdata
