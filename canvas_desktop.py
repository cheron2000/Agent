"""canvas_desktop.py - Native AI Desktop Canvas Window (PyQt6).

A dedicated, isolated desktop workspace canvas designed exclusively for AI control:
- High-resolution bordered canvas with real-time AI status HUD.
- Full Chromium engine (QWebEngineView) embedded directly inside the canvas.
- Strict spatial bounding: Eyes & Hands operate strictly within this canvas viewport.
- Ephemeral lifecycle: Screenshots are tracked during task execution and auto-deleted upon task end.
"""

import json
import os
import sys
import time
from typing import Optional, Tuple

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from PyQt6.QtCore import QPoint, QTimer, QUrl, pyqtSignal, QObject
from PyQt6.QtWebEngineCore import QWebEngineSettings
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

CANVAS_STATE_FILE = os.path.join(os.path.dirname(__file__), "canvas_state.json")


class CanvasSignals(QObject):
    navigate = pyqtSignal(str)
    set_status = pyqtSignal(str, str)  # (state, message)
    focus_window = pyqtSignal()


class AIDesktopCanvas(QMainWindow):
    """Native AI-controlled Desktop Workspace Canvas."""

    def __init__(self, initial_url: str = "https://chatgpt.com", width: int = 1280, height: int = 820):
        super().__init__()
        self.setWindowTitle("🤖 AI Desktop Workspace — [AI Controlled Canvas]")
        self.resize(width, height)
        self.setMinimumSize(800, 600)

        self.signals = CanvasSignals()
        self.signals.navigate.connect(self._do_navigate)
        self.signals.set_status.connect(self._do_set_status)
        self.signals.focus_window.connect(self._do_focus)

        self._build_ui(initial_url)
        self._setup_style()

        # Thread-safe periodic state sync on Qt main event loop
        self.state_timer = QTimer(self)
        self.state_timer.timeout.connect(self.update_state_file)
        self.state_timer.start(1000)

    def _build_ui(self, initial_url: str):
        central = QWidget(self)
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # ── Top AI Control Bar (HUD) ─────────────────────────────────────────
        self.hud_frame = QFrame()
        self.hud_frame.setObjectName("hudFrame")
        hud_layout = QHBoxLayout(self.hud_frame)
        hud_layout.setContentsMargins(12, 6, 12, 6)
        hud_layout.setSpacing(12)

        # Badge
        self.badge = QLabel("● AI CONTROL ACTIVE")
        self.badge.setObjectName("badgeActive")
        hud_layout.addWidget(self.badge)

        # Status text
        self.status_label = QLabel("🟢 IDLE — Ready for AI task")
        self.status_label.setObjectName("statusLabel")
        hud_layout.addWidget(self.status_label, 1)

        # Bounds monitor
        self.bounds_label = QLabel("Viewport: Calculating...")
        self.bounds_label.setObjectName("boundsLabel")
        hud_layout.addWidget(self.bounds_label)

        # Ephemeral storage badge
        self.ephemeral_label = QLabel("📸 Ephemeral Storage [Auto-Purge]")
        self.ephemeral_label.setObjectName("ephemeralLabel")
        hud_layout.addWidget(self.ephemeral_label)

        layout.addWidget(self.hud_frame)

        # ── Address Bar / Navigation Controls ────────────────────────────────
        nav_frame = QFrame()
        nav_frame.setObjectName("navFrame")
        nav_layout = QHBoxLayout(nav_frame)
        nav_layout.setContentsMargins(8, 4, 8, 4)
        nav_layout.setSpacing(8)

        self.url_input = QLineEdit(initial_url)
        self.url_input.setObjectName("urlInput")
        self.url_input.returnPressed.connect(self._on_url_submitted)
        nav_layout.addWidget(self.url_input, 1)

        btn_go = QPushButton("Go")
        btn_go.setObjectName("navBtn")
        btn_go.clicked.connect(self._on_url_submitted)
        nav_layout.addWidget(btn_go)

        btn_refresh = QPushButton("↻")
        btn_refresh.setObjectName("navBtn")
        btn_refresh.clicked.connect(self._reload_page)
        nav_layout.addWidget(btn_refresh)

        layout.addWidget(nav_frame)

        # ── Embedded Canvas Viewport (Chromium Engine) ──────────────────────
        self.canvas_container = QFrame()
        self.canvas_container.setObjectName("canvasContainer")
        container_layout = QVBoxLayout(self.canvas_container)
        container_layout.setContentsMargins(4, 4, 4, 4)

        self.web_view = QWebEngineView()
        self.web_view.setObjectName("webView")

        # Configure custom browser settings
        profile = self.web_view.page().profile()
        profile.setHttpUserAgent(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        settings = self.web_view.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalStorageEnabled, True)

        self.web_view.load(QUrl(initial_url))
        self.web_view.urlChanged.connect(lambda qurl: self.url_input.setText(qurl.toString()))

        container_layout.addWidget(self.web_view)
        layout.addWidget(self.canvas_container, 1)

    def _setup_style(self):
        self.setStyleSheet("""
            QMainWindow {
                background-color: #0b0f19;
            }
            #hudFrame {
                background-color: #111827;
                border: 1px solid #1f2937;
                border-radius: 6px;
            }
            #badgeActive {
                color: #00d2ff;
                font-weight: bold;
                font-size: 11px;
                background-color: rgba(0, 210, 255, 0.15);
                padding: 4px 8px;
                border-radius: 4px;
                border: 1px solid rgba(0, 210, 255, 0.4);
            }
            #statusLabel {
                color: #e5e7eb;
                font-weight: 500;
                font-size: 12px;
            }
            #boundsLabel {
                color: #9ca3af;
                font-family: Consolas, monospace;
                font-size: 11px;
                background-color: #1f2937;
                padding: 3px 6px;
                border-radius: 4px;
            }
            #ephemeralLabel {
                color: #10b981;
                font-size: 11px;
                font-weight: 500;
                background-color: rgba(16, 185, 129, 0.12);
                padding: 3px 6px;
                border-radius: 4px;
                border: 1px solid rgba(16, 185, 129, 0.3);
            }
            #navFrame {
                background-color: #111827;
                border: 1px solid #1f2937;
                border-radius: 6px;
            }
            #urlInput {
                background-color: #0d1117;
                color: #f3f4f6;
                border: 1px solid #374151;
                border-radius: 4px;
                padding: 4px 10px;
                font-size: 12px;
            }
            #navBtn {
                background-color: #1f2937;
                color: #e5e7eb;
                border: 1px solid #374151;
                border-radius: 4px;
                padding: 4px 10px;
                font-size: 12px;
            }
            #navBtn:hover {
                background-color: #374151;
                color: #ffffff;
            }
            #canvasContainer {
                background-color: #0d1117;
                border: 2px solid #00d2ff;
                border-radius: 6px;
            }
        """)

    def get_viewport_bounds(self) -> Tuple[int, int, int, int]:
        """Calculate exact global screen coordinates (x, y, width, height) of the canvas viewport."""
        global_top_left = self.web_view.mapToGlobal(QPoint(0, 0))
        x = int(global_top_left.x())
        y = int(global_top_left.y())
        w = int(self.web_view.width())
        h = int(self.web_view.height())
        return (x, y, w, h)

    def update_state_file(self):
        """Save current canvas bounds to state file so Eyes and Hands can bind immediately."""
        bounds = self.get_viewport_bounds()
        self.bounds_label.setText(f"Canvas: {bounds[2]}x{bounds[3]} at ({bounds[0]}, {bounds[1]})")
        try:
            hwnd_val = str(int(self.winId()))
        except Exception:
            hwnd_val = str(self.winId())
        data = {
            "bounds": list(bounds),
            "width": bounds[2],
            "height": bounds[3],
            "x": bounds[0],
            "y": bounds[1],
            "hwnd": hwnd_val,
            "timestamp": time.time(),
        }
        try:
            with open(CANVAS_STATE_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass

    def moveEvent(self, event):
        super().moveEvent(event)
        self.update_state_file()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update_state_file()

    def showEvent(self, event):
        super().showEvent(event)
        self.update_state_file()

    def _on_url_submitted(self):
        url = self.url_input.text().strip()
        if not url.startswith("http://") and not url.startswith("https://"):
            url = "https://" + url
        self.web_view.load(QUrl(url))

    def _reload_page(self):
        self.web_view.reload()

    def _do_navigate(self, url: str):
        if not url.startswith("http://") and not url.startswith("https://"):
            url = "https://" + url
        self.url_input.setText(url)
        self.web_view.load(QUrl(url))

    def _do_set_status(self, state: str, message: str):
        icons = {
            "idle": "🟢 IDLE",
            "perceiving": "🔵 EYES PERCEIVING",
            "executing": "🟠 HANDS EXECUTING",
            "transcribing": "🟣 OCR TRANSCRIBING",
            "complete": "✅ TASK COMPLETE",
        }
        icon_str = icons.get(state.lower(), "● AI ACTIVE")
        self.status_label.setText(f"{icon_str} — {message}")

    def _do_focus(self):
        self.activateWindow()
        self.raise_()


# ── Global Controller Functions ───────────────────────────────────────────────

def get_canvas_bounds() -> Optional[Tuple[int, int, int, int]]:
    """Retrieve the current active AI canvas boundaries from the shared state file."""
    if os.path.exists(CANVAS_STATE_FILE):
        try:
            with open(CANVAS_STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                b = data.get("bounds")
                if b and len(b) == 4:
                    return tuple(b)
        except Exception:
            pass
    return None


def ensure_default_desktop():
    """Ensure the window is rendered on the interactive Default desktop so the user sees it."""
    try:
        import ctypes
        hDesk = ctypes.windll.user32.OpenDesktopW("Default", 0, False, 0x01FF)
        if hDesk:
            ctypes.windll.user32.SetThreadDesktop(hDesk)
            print("[Canvas Desktop] Attached to interactive User Desktop (Default).")
    except Exception as e:
        print(f"[Canvas Desktop] Desktop attach note: {e}")


def run_canvas_app(initial_url: str = "https://www.swiggy.com/instamart", width: int = 1280, height: int = 820):
    """Launch the AI Desktop Canvas application."""
    ensure_default_desktop()
    app = QApplication.instance()
    if not app:
        app = QApplication(sys.argv)

    window = AIDesktopCanvas(initial_url=initial_url, width=width, height=height)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else "https://chatgpt.com"
    run_canvas_app(initial_url=url)
