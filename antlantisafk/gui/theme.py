"""Dark theme constants, application stylesheet, and generated app icon.

The app ships no binary assets: the icon is drawn programmatically so the
repository stays text-only and PyInstaller bundles stay small. A real
``assets/icon.ico`` can be added later and :func:`build_app_icon` will
prefer it when present.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import (
    QColor,
    QFont,
    QIcon,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import QApplication

#: Name of a bundled icon file (optional, takes precedence when present).
ICON_FILENAME = "icon.ico"

COLORS: dict[str, str] = {
    "bg": "#10131a",
    "card": "#181c26",
    "card_border": "#232936",
    "accent": "#4f8cff",
    "accent_hover": "#6da0ff",
    "success": "#3ecf8e",
    "warning": "#f5a623",
    "danger": "#e5534b",
    "text": "#e8eaf0",
    "muted": "#98a1b3",
    "input_bg": "#0d1016",
}

STATUS_COLORS: dict[str, str] = {
    "ok": COLORS["success"],
    "busy": COLORS["accent"],
    "warn": COLORS["warning"],
    "err": COLORS["danger"],
    "idle": COLORS["muted"],
}

FONT_STACK = 'font-family: "Segoe UI", "Inter", sans-serif;'


def build_stylesheet() -> str:
    """Return the application-wide QSS stylesheet (readable, roomy sizing)."""
    c = COLORS
    return f"""
    QWidget {{
        {FONT_STACK} color: {c['text']};
        background: {c['bg']};
        font-size: 14px;
    }}
    QLabel#Title {{ font-size: 22px; font-weight: 600; }}
    QLabel#Subtitle {{ color: {c['muted']}; font-size: 13px; }}
    QLabel#Disclaimer {{ color: {c['warning']}; font-size: 12px; }}

    QFrame#Card {{
        background: {c['card']};
        border: 1px solid {c['card_border']};
        border-radius: 12px;
    }}
    QLabel#CardTitle {{
        color: {c['muted']};
        font-size: 12px;
        font-weight: 600;
        letter-spacing: 1px;
    }}

    QLineEdit, QSpinBox {{
        background: {c['input_bg']};
        border: 1px solid {c['card_border']};
        border-radius: 6px;
        padding: 7px 10px;
        font-size: 14px;
        min-height: 22px;
        selection-background-color: {c['accent']};
    }}
    QLineEdit:focus, QSpinBox:focus {{ border-color: {c['accent']}; }}
    QSpinBox::up-button, QSpinBox::down-button {{ width: 18px; }}

    QPushButton {{
        background: {c['card']};
        border: 1px solid {c['card_border']};
        border-radius: 6px;
        padding: 8px 16px;
        font-size: 14px;
        min-height: 20px;
    }}
    QPushButton:hover {{ border-color: {c['accent']}; }}
    QPushButton:disabled {{ color: {c['muted']}; }}

    QPushButton#Primary {{
        background: {c['accent']};
        border: none;
        font-weight: 600;
        padding: 9px 20px;
    }}
    QPushButton#Primary:hover {{ background: {c['accent_hover']}; }}
    QPushButton#Danger {{ border-color: {c['danger']}; color: {c['danger']}; }}
    QPushButton#Danger:hover {{ background: rgba(229, 83, 75, 0.12); }}

    QPlainTextEdit#LogView {{
        background: {c['input_bg']};
        border: 1px solid {c['card_border']};
        border-radius: 6px;
        font-family: "Cascadia Mono", Consolas, monospace;
        font-size: 12px;
    }}

    QCheckBox {{ spacing: 8px; font-size: 14px; }}
    QCheckBox::indicator {{ width: 16px; height: 16px; }}
    QToolTip {{
        background: {c['card']};
        color: {c['text']};
        border: 1px solid {c['card_border']};
        font-size: 13px;
        padding: 4px;
    }}
    """


def _bundled_icon_path() -> Path | None:
    """Return the bundled icon.ico path if present (source or frozen)."""
    import sys

    if getattr(sys, "frozen", False):
        base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    else:
        base = Path(__file__).resolve().parent.parent
    for candidate in (base / "assets" / ICON_FILENAME, base / ICON_FILENAME):
        if candidate.exists():
            return candidate
    return None


def build_app_icon() -> QIcon:
    """Build the application icon.

    Prefers a bundled ``icon.ico``; otherwise draws a rounded gradient tile
    with a stylised wave/'A' mark so the tray icon looks intentional even
    without binary assets.
    """
    bundled = _bundled_icon_path()
    if bundled is not None:
        icon = QIcon(str(bundled))
        if not icon.isNull():
            return icon

    size = 128
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)

    grad = QLinearGradient(0, 0, size, size)
    grad.setColorAt(0.0, QColor(COLORS["accent"]))
    grad.setColorAt(1.0, QColor("#7b5cff"))
    path = QPainterPath()
    path.addRoundedRect(QRectF(4, 4, size - 8, size - 8), 28, 28)
    painter.fillPath(path, grad)

    # Wave mark across the lower half (the 'Atlantis' motif).
    pen = QPen(QColor("white"))
    pen.setWidthF(9)
    pen.setCapStyle(Qt.RoundCap)
    painter.setPen(pen)
    painter.drawArc(QRectF(18, 52, 44, 40), 180 * 16, 180 * 16)
    painter.drawArc(QRectF(62, 52, 44, 40), 180 * 16, 180 * 16)

    # 'A' mark in the upper area.
    painter.setFont(QFont("Segoe UI", 46, QFont.Bold))
    painter.drawText(QRectF(0, 2, size, 64), Qt.AlignCenter, "A")

    painter.end()
    return QIcon(pixmap)


def apply_theme(app: QApplication) -> None:
    """Apply the stylesheet and icon to the application."""
    app.setStyleSheet(build_stylesheet())
    app.setWindowIcon(build_app_icon())
