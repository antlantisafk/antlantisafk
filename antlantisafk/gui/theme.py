"""AtlantisAFK ocean design system: palette, spacing tokens, QSS, branding.

Visual identity comes from the AtlantisAFK wave logo: deep-ocean navy
surfaces with luminous wave-blue accents. All spacing/sizing derives from
the tokens below so the layout stays consistent and airy.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QApplication

#: Name of the bundled icon file (multi-size .ico generated from the logo).
ICON_FILENAME = "icon.ico"
WORDMARK_FILENAME = "wordmark.png"
WAVE_ICON_FILENAME = "wave_icon.png"

# ---------------------------------------------------------------------------
# Palette (derived from the wave logo)
# ---------------------------------------------------------------------------

COLORS: dict[str, str] = {
    "bg": "#0B1220",            # deep ocean floor
    "bg_gradient": "#0E1730",   # subtle vertical lift
    "card": "#121A2B",          # raised surface
    "card_hover": "#16203A",
    "card_border": "#1E2A44",
    "accent": "#2196F3",        # wave blue
    "accent_bright": "#38BDF8", # crest cyan
    "accent_deep": "#1565C0",
    "success": "#34D399",
    "warning": "#FBBF24",
    "danger": "#F87171",
    "text": "#EAF2FF",
    "muted": "#8FA3C0",
    "input_bg": "#0A101D",
    "input_border": "#24304E",
}

STATUS_COLORS: dict[str, str] = {
    "ok": COLORS["success"],
    "busy": COLORS["accent_bright"],
    "warn": COLORS["warning"],
    "err": COLORS["danger"],
    "idle": COLORS["muted"],
}

# ---------------------------------------------------------------------------
# Spacing / sizing tokens
# ---------------------------------------------------------------------------

SPACE: dict[str, int] = {
    "xs": 4,
    "sm": 8,
    "md": 12,
    "lg": 16,
    "xl": 22,
    "xxl": 30,
}

RADIUS: dict[str, int] = {"sm": 8, "md": 12, "lg": 16}

WINDOW_MAX_WIDTH: int = 880
CONTENT_MAX_WIDTH: int = 820

FONT_STACK = 'font-family: "Segoe UI", "Inter", sans-serif;'
MONO_STACK = 'font-family: "Cascadia Mono", Consolas, monospace;'


def build_stylesheet() -> str:
    """Return the application-wide QSS stylesheet."""
    c = COLORS
    r = RADIUS
    return f"""
    QWidget {{
        {FONT_STACK} color: {c['text']};
        background: {c['bg']};
        font-size: 14px;
    }}
    QMainWindow, QDialog {{ background: {c['bg']}; }}
    /* Labels/checkboxes are overlays on cards — never paint their own bg. */
    QLabel, QCheckBox, QRadioButton {{ background: transparent; }}

    QLabel#Title {{ font-size: 15px; font-weight: 600; color: {c['muted']}; }}
    QLabel#Subtitle {{ color: {c['muted']}; font-size: 13px; }}
    QLabel#Disclaimer {{
        color: {c['warning']}; font-size: 12px; background: transparent;
    }}
    QLabel#StatValue {{
        font-size: 22px; font-weight: 700; color: {c['text']};
    }}
    QLabel#StatLabel {{
        font-size: 11px; font-weight: 600; color: {c['muted']};
        letter-spacing: 1px;
    }}
    QLabel#CardTitle {{
        color: {c['accent_bright']}; font-size: 12px; font-weight: 700;
        letter-spacing: 2px;
    }}

    QFrame#Card {{
        background: {c['card']};
        border: 1px solid {c['card_border']};
        border-radius: {r['lg']}px;
    }}
    QFrame#Card:hover {{ border-color: {c['accent_deep']}; }}

    QFrame#StatusPill {{
        background: {c['input_bg']};
        border: 1px solid {c['input_border']};
        border-radius: 14px;
    }}
    QLabel#VersionChip {{
        color: {c['muted']}; font-size: 11px; font-weight: 600;
        background: {c['card']};
        border: 1px solid {c['card_border']};
        border-radius: 10px; padding: 2px 10px;
    }}

    QLineEdit, QSpinBox {{
        background: {c['input_bg']};
        border: 1px solid {c['input_border']};
        border-radius: {r['sm']}px;
        padding: 9px 12px;
        font-size: 14px;
        min-height: 24px;
        selection-background-color: {c['accent']};
    }}
    QLineEdit:focus, QSpinBox:focus {{
        border-color: {c['accent']};
        background: {c['card_hover']};
    }}
    QSpinBox::up-button, QSpinBox::down-button {{ width: 20px; }}

    QPushButton {{
        background: {c['card']};
        border: 1px solid {c['input_border']};
        border-radius: {r['sm']}px;
        padding: 10px 20px;
        font-size: 14px;
        font-weight: 600;
        min-height: 22px;
    }}
    QPushButton:hover {{ border-color: {c['accent']}; background: {c['card_hover']}; }}
    QPushButton:disabled {{
        color: {c['muted']};
        border-color: {c['card_border']};
        background: {c['card']};
    }}

    QPushButton#Primary {{
        background: {c['accent']};
        border: 1px solid {c['accent']};
        color: #06121F;
        font-size: 15px;
        font-weight: 700;
        padding: 12px 30px;
    }}
    QPushButton#Primary:hover {{ background: {c['accent_bright']}; border-color: {c['accent_bright']}; }}
    QPushButton#Primary:disabled {{
        background: {c['card']}; color: {c['muted']}; border-color: {c['card_border']};
    }}

    QPushButton#Danger {{
        background: transparent;
        border: 1px solid {c['danger']};
        color: {c['danger']};
    }}
    QPushButton#Danger:hover {{ background: rgba(248, 113, 113, 0.12); }}
    QPushButton#Danger:disabled {{
        color: {c['muted']}; border-color: {c['card_border']}; background: transparent;
    }}

    QFrame#StatTile {{
        background: {c['input_bg']};
        border: 1px solid {c['card_border']};
        border-radius: {r['md']}px;
    }}
    QFrame#HeroBanner {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 {c['bg_gradient']}, stop:1 {c['bg']});
        border: 1px solid {c['card_border']};
        border-radius: {r['lg']}px;
    }}

    QPlainTextEdit#LogView {{
        background: {c['input_bg']};
        border: 1px solid {c['card_border']};
        border-radius: {r['md']}px;
        {MONO_STACK} font-size: 12px;
    }}

    QCheckBox {{ spacing: 8px; font-size: 14px; }}
    QCheckBox::indicator {{ width: 17px; height: 17px; }}

    QToolTip {{
        background: {c['card']}; color: {c['text']};
        border: 1px solid {c['input_border']};
        font-size: 13px; padding: 6px;
    }}

    QScrollBar:vertical {{
        background: transparent; width: 10px; margin: 2px;
    }}
    QScrollBar::handle:vertical {{
        background: {c['input_border']}; border-radius: 4px; min-height: 30px;
    }}
    QScrollBar::handle:vertical:hover {{ background: {c['accent_deep']}; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    """


# ---------------------------------------------------------------------------
# Asset loading (source tree and PyInstaller bundle)
# ---------------------------------------------------------------------------


def _asset_dir() -> Path:
    import sys

    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent)) / "assets"
    return Path(__file__).resolve().parent.parent.parent / "assets"


def _asset(name: str) -> Path | None:
    path = _asset_dir() / name
    return path if path.exists() else None


def bundled_icon_path() -> Path | None:
    """Return the bundled ``icon.ico`` path if present."""
    return _asset(ICON_FILENAME)


def build_app_icon() -> QIcon:
    """The wave logo as the application/window/tray icon."""
    path = bundled_icon_path()
    if path is not None:
        icon = QIcon(str(path))
        if not icon.isNull():
            return icon
    # Fallback: simple wave-blue rounded square (should never happen).
    pixmap = QPixmap(128, 128)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setBrush(QColor(COLORS["accent"]))
    painter.setPen(Qt.NoPen)
    painter.drawRoundedRect(QRectF(8, 8, 112, 112), 28, 28)
    painter.end()
    return QIcon(pixmap)


def build_wordmark_pixmap(height: int = 54) -> QPixmap | None:
    """The AtlantisAFK wordmark scaled to ``height`` px, keeping aspect."""
    path = _asset(WORDMARK_FILENAME)
    if path is None:
        return None
    pixmap = QPixmap(str(path))
    if pixmap.isNull():
        return None
    return pixmap.scaledToHeight(height, Qt.SmoothTransformation)


def build_wave_pixmap(size: int = 40) -> QPixmap | None:
    """The wave icon scaled to ``size`` px for inline header use."""
    path = _asset(WAVE_ICON_FILENAME)
    if path is None:
        return None
    pixmap = QPixmap(str(path))
    if pixmap.isNull():
        return None
    return pixmap.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)


def apply_theme(app: QApplication) -> None:
    """Apply the stylesheet, icon, and default UI font to the application."""
    app.setStyleSheet(build_stylesheet())
    app.setWindowIcon(build_app_icon())
    font = QFont("Segoe UI", 10)
    app.setFont(font)
