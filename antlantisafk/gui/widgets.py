"""Reusable GUI widgets for AntlantisAFK."""

from __future__ import annotations

import logging
import time

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPalette, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from .theme import COLORS, STATUS_COLORS


class StatusPill(QWidget):
    """A coloured dot + text indicator for account/connection status."""

    def __init__(self, text: str = "Unknown", color: str = "idle",
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        # Horizontal row: coloured dot beside the text (never stacked).
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self._dot = QLabel()
        self._dot.setFixedSize(14, 14)
        self._text = QLabel(text)
        bold = QFont()
        bold.setWeight(QFont.DemiBold)
        bold.setPointSize(10)
        self._text.setFont(bold)
        layout.addWidget(self._dot, 0, Qt.AlignVCenter)
        layout.addWidget(self._text, 0, Qt.AlignVCenter)
        layout.addStretch(1)  # keep the pill compact inside form cells
        self.set_status(text, color)

    def set_status(self, text: str, color_key: str) -> None:
        """Update label text and dot colour (``color_key`` in STATUS_COLORS)."""
        self._text.setText(text)
        hex_color = STATUS_COLORS.get(color_key, STATUS_COLORS["idle"])
        pixmap = QPixmap(14, 14)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setBrush(QColor(hex_color))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(2, 2, 10, 10)
        painter.end()
        self._dot.setPixmap(pixmap)


class Card(QFrame):
    """A titled, rounded content container."""

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(14, 12, 14, 14)
        self._layout.setSpacing(8)
        label = QLabel(title)
        label.setObjectName("CardTitle")
        self._layout.addWidget(label)

    def body(self) -> QVBoxLayout:
        """The layout widgets should be added to."""
        return self._layout


class _QtLogHandler(logging.Handler):
    """Logging handler that appends formatted records to the log panel."""

    def __init__(self, panel: "LogPanel") -> None:
        super().__init__(level=logging.INFO)
        self._panel = panel

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            self._panel.append_log(msg, record.levelname)
        except Exception:  # noqa: BLE001 - never crash on logging
            pass


class LogPanel(QPlainTextEdit):
    """Read-only, auto-scrolling log view showing INFO and above."""

    MAX_BLOCKS = 1000  # keep memory bounded

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("LogView")
        self.setReadOnly(True)
        self.setMaximumBlockCount(self.MAX_BLOCKS)
        self.setPlaceholderText("Log output appears here…")

    def append_log(self, message: str, level: str = "INFO") -> None:
        """Append one coloured, timestamped log line."""
        colors = {
            "INFO": COLORS["text"],
            "WARNING": STATUS_COLORS["warn"],
            "ERROR": STATUS_COLORS["err"],
            "CRITICAL": STATUS_COLORS["err"],
            "DEBUG": COLORS["muted"],
        }
        hex_color = colors.get(level.upper(), COLORS["text"])
        timestamp = time.strftime("%H:%M:%S")
        safe = (message.replace("&", "&amp;").replace("<", "&lt;")
                .replace(">", "&gt;"))
        self.appendHtml(
            f'<span style="color:{COLORS["muted"]}">{timestamp}</span> '
            f'<span style="color:{hex_color}">{safe}</span>'
        )

    def attach_to_logger(self, logger: logging.Logger | None = None) -> None:
        """Start mirroring Python log records into this panel."""
        handler = _QtLogHandler(self)
        handler.setFormatter(logging.Formatter("%(name)s: %(message)s"))
        target = logger if logger is not None else logging.getLogger()
        target.addHandler(handler)
