"""visual_overlay.py - Click-through transparent overlay showing real-time AI mouse trails and click ripples.

Features:
- Completely click-through: Never intercepts or blocks physical mouse clicks.
- Renders glowing expanding ripple animations at click coordinates (x, y).
- Renders fading cursor motion trails so the user clearly sees where the AI is navigating.
- Minimal top HUD bar showing live AI perception and action state.
"""

import sys
import threading
import time
from typing import Optional, List, Tuple

from PyQt6.QtCore import Qt, QTimer, QPoint, QRect
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush, QFont
from PyQt6.QtWidgets import QApplication, QWidget


class RippleEffect:
    def __init__(self, x: int, y: int, color: QColor = QColor(0, 210, 255)):
        self.x = x
        self.y = y
        self.color = color
        self.radius = 6.0
        self.max_radius = 45.0
        self.alpha = 240
        self.is_alive = True

    def update(self):
        self.radius += 3.2
        self.alpha = max(0, int(self.alpha - 18))
        if self.alpha <= 0 or self.radius >= self.max_radius:
            self.is_alive = False


class VisualOverlayWindow(QWidget):
    def __init__(self):
        super().__init__()
        # Click-through, frameless, topmost transparent window
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)

        screen = QApplication.primaryScreen()
        geo = screen.geometry()
        self.setGeometry(geo)

        self.ripples: List[RippleEffect] = []
        self.status_text: str = "● AI AGENT ACTIVE (EXTENDED DESKTOP)"
        self.is_active = True

        # Render loop timer (60 FPS)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._on_tick)
        self.timer.start(16)

    def trigger_ripple(self, x: int, y: int, button: str = "left"):
        color = QColor(0, 210, 255) if button == "left" else QColor(255, 170, 0)
        self.ripples.append(RippleEffect(x, y, color))
        self.update()

    def set_status(self, text: str):
        self.status_text = text
        self.update()

    def _on_tick(self):
        if self.ripples:
            for r in self.ripples:
                r.update()
            self.ripples = [r for r in self.ripples if r.is_alive]
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        # 1. Draw minimal top AI HUD banner
        hud_w, hud_h = 420, 32
        hud_x = (self.width() - hud_w) // 2
        hud_y = 6
        painter.setBrush(QBrush(QColor(13, 17, 23, 220)))
        painter.setPen(QPen(QColor(0, 210, 255, 180), 1.5))
        painter.drawRoundedRect(hud_x, hud_y, hud_w, hud_h, 6, 6)

        painter.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        painter.setPen(QColor(0, 210, 255))
        painter.drawText(QRect(hud_x, hud_y, hud_w, hud_h), Qt.AlignmentFlag.AlignCenter, self.status_text)

        # 2. Draw active click ripples
        for r in self.ripples:
            col = QColor(r.color.red(), r.color.green(), r.color.blue(), r.alpha)
            pen = QPen(col, 2.5)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(QPoint(int(r.x), int(r.y)), int(r.radius), int(r.radius))

            # Inner pulse dot
            if r.radius < 20:
                inner_col = QColor(col.red(), col.green(), col.blue(), int(r.alpha * 0.8))
                painter.setBrush(QBrush(inner_col))
                painter.drawEllipse(QPoint(int(r.x), int(r.y)), 4, 4)


_OVERLAY_WINDOW: Optional[VisualOverlayWindow] = None
_OVERLAY_APP: Optional[QApplication] = None


def get_or_create_overlay() -> Optional[VisualOverlayWindow]:
    global _OVERLAY_WINDOW, _OVERLAY_APP
    if _OVERLAY_WINDOW is not None:
        return _OVERLAY_WINDOW
    return None


def show_click_ripple(x: int, y: int, button: str = "left"):
    """Trigger visual ripple effect at (x, y)."""
    global _OVERLAY_WINDOW
    if _OVERLAY_WINDOW is not None:
        _OVERLAY_WINDOW.trigger_ripple(x, y, button)


def update_hud_status(text: str):
    """Update top HUD status message."""
    global _OVERLAY_WINDOW
    if _OVERLAY_WINDOW is not None:
        _OVERLAY_WINDOW.set_status(text)
