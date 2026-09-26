"""Smoke tests: every module must import cleanly and key widgets must build.

Catches missing imports / syntax errors in GUI modules that unit tests
otherwise never touch. Skipped automatically when PySide6 is unavailable.
"""

from __future__ import annotations

import importlib

import pytest

pyqt = pytest.importorskip("PySide6", reason="PySide6 not installed")


def test_all_modules_import() -> None:
    """Import every module in the package — no NameError/ImportError allowed."""
    import antlantisafk

    package_root = antlantisafk.__path__[0]
    import pathlib

    modules = [
        "antlantisafk",
        "antlantisafk.constants",
        "antlantisafk.config",
        "antlantisafk.logging_setup",
        "antlantisafk.status",
        "antlantisafk.utils.validators",
        "antlantisafk.security.token_store",
        "antlantisafk.security.single_instance",
        "antlantisafk.auth.manager",
        "antlantisafk.minecraft.session",
        "antlantisafk.minecraft.worker_bridge",
    ]
    # Auto-discover the GUI modules so new ones are covered too.
    for path in pathlib.Path(package_root).rglob("*.py"):
        rel = path.relative_to(package_root).with_suffix("")
        parts = list(rel.parts)
        if parts and parts[-1] == "__init__":
            parts = parts[:-1]
        if not parts:  # package-root __init__, already imported above
            continue
        name = "antlantisafk." + ".".join(parts)
        if name not in modules:
            modules.append(name)

    for name in modules:
        importlib.import_module(name)


def test_widgets_construct_with_app(qtbot) -> None:
    """StatusPill, Card, and LogPanel must build without errors."""
    qtbot  # fixture ensures a QApplication exists
    from antlantisafk.gui.theme import build_app_icon, build_stylesheet
    from antlantisafk.gui.widgets import Card, LogPanel, StatusPill

    pill = StatusPill("Connected", "ok")
    assert pill._text.text() == "Connected"
    card = Card("Test card")
    assert card.body() is not None
    panel = LogPanel()
    panel.append_log("hello", "INFO")
    assert "hello" in panel.toPlainText()
    # Theme helpers must not crash either.
    assert build_stylesheet()
    assert not build_app_icon().isNull()
