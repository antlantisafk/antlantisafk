"""Reusable GUI widgets for AtlantisAFK."""

from __future__ import annotations

import logging
import time

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from .theme import COLORS, STATUS_COLORS


class StatusPill(QFrame):
    """A capsule status indicator: glowing dot + bold text.

    Supports a soft pulse animation for transient states (connecting /
    reconnecting) via :meth:`set_pulse`.
    """

    _PULSE_STEPS = (255, 200, 150, 100, 150, 200)  # breathing alpha cycle

    def __init__(self, text: str = "Unknown", color: str = "idle",
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("StatusPill")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 5, 14, 5)
        layout.setSpacing(8)
        self._dot = QLabel()
        self._dot.setFixedSize(12, 12)
        self._text = QLabel(text)
        bold = QFont()
        bold.setWeight(QFont.DemiBold)
        bold.setPointSize(10)
        self._text.setFont(bold)
        layout.addWidget(self._dot, 0, Qt.AlignVCenter)
        layout.addWidget(self._text, 0, Qt.AlignVCenter)

        self._hex_color = STATUS_COLORS.get(color, STATUS_COLORS["idle"])
        self._pulse_enabled = False
        self._pulse_index = 0
        self._timer = QTimer(self)
        self._timer.setInterval(220)
        self._timer.timeout.connect(self._pulse_tick)
        self.set_status(text, color)

    # -- public API -----------------------------------------------------

    def set_status(self, text: str, color_key: str) -> None:
        """Update label text and dot colour (``color_key`` in STATUS_COLORS)."""
        self._text.setText(text)
        self._hex_color = STATUS_COLORS.get(color_key, STATUS_COLORS["idle"])
        self._text.setStyleSheet(f"color: {self._hex_color};")
        self._render_dot(255)

    def set_pulse(self, enabled: bool) -> None:
        """Start/stop the breathing animation on the dot."""
        if enabled and not self._pulse_enabled:
            self._pulse_enabled = True
            self._timer.start()
        elif not enabled and self._pulse_enabled:
            self._pulse_enabled = False
            self._timer.stop()
            self._render_dot(255)

    # -- internals --------------------------------------------------------

    def _pulse_tick(self) -> None:
        self._pulse_index = (self._pulse_index + 1) % len(self._PULSE_STEPS)
        self._render_dot(self._PULSE_STEPS[self._pulse_index])

    def _render_dot(self, alpha: int) -> None:
        pixmap = QPixmap(12, 12)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing, True)
        color = QColor(self._hex_color)
        color.setAlpha(alpha)
        painter.setBrush(color)
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(1, 1, 10, 10)
        # Soft glow ring at reduced alpha.
        glow = QColor(self._hex_color)
        glow.setAlpha(int(alpha * 0.28))
        painter.setBrush(glow)
        painter.drawEllipse(0, 0, 12, 12)
        painter.end()
        self._dot.setPixmap(pixmap)


class Card(QFrame):
    """A titled, rounded content container with an optional header action."""

    def __init__(self, title: str, action: QWidget | None = None,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(16, 14, 16, 16)
        self._layout.setSpacing(10)
        header = QHBoxLayout()
        header.setSpacing(8)
        label = QLabel(title)
        label.setObjectName("CardTitle")
        header.addWidget(label)
        header.addStretch(1)
        if action is not None:
            header.addWidget(action, 0, Qt.AlignVCenter)
        self._layout.addLayout(header)

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
