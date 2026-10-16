"""canvas_desktop.py — PyQt6 native desktop canvas window for the AI agent.

Runs as a standalone process:  python canvas_desktop.py [url]

The window is a QMainWindow containing a full Chromium browser (QWebEngineView)
plus a status HUD.  On every move/resize/show event the window writes its exact
global screen coordinates into canvas_state.json so ai_controller.py can read
the live bounds without any IPC server.  A 1-second background timer keeps the
file fresh while the window is visible.
"""

import json
import os
import sys
import time
import logging

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CANVAS_STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "canvas_state.json")

# ---------------------------------------------------------------------------
# Module-level logger
# ---------------------------------------------------------------------------

_log_formatter = logging.Formatter("%(asctime)s %(levelname)s [canvas_desktop] %(message)s")

_file_handler = logging.FileHandler(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "canvas_debug.log"),
    encoding="utf-8",
)
_file_handler.setFormatter(_log_formatter)

_console_handler = logging.StreamHandler()
_console_handler.setFormatter(_log_formatter)

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
logger.addHandler(_file_handler)
logger.addHandler(_console_handler)


# ---------------------------------------------------------------------------
# IPC helper — read canvas bounds written by the running canvas window
# ---------------------------------------------------------------------------

def get_canvas_bounds() -> tuple:
    """Return the current canvas viewport bounds as (x, y, width, height).

    Raises:
        RuntimeError: If canvas_state.json does not exist, cannot be parsed,
                      or is missing the 'bounds' key or has an invalid value.

    Logs a warning if the state file is more than 5 seconds old (stale).
    """
    if not os.path.exists(CANVAS_STATE_FILE):
        raise RuntimeError("canvas_state.json not found; is canvas_desktop.py running?")

    try:
        with open(CANVAS_STATE_FILE, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception as e:
        raise RuntimeError(f"Failed to read canvas_state.json: {e}") from e

    if "bounds" not in data:
        raise RuntimeError("canvas_state.json is missing the 'bounds' key")

    age = time.time() - data.get("timestamp", 0)
    if age > 5.0:
        logger.warning(
            "canvas_state.json is stale (%.1fs old); bounds may be inaccurate", age
        )

    b = data["bounds"]
    if not b or len(b) != 4:
        raise RuntimeError("canvas_state.json bounds value is invalid")

    return tuple(b)


# ---------------------------------------------------------------------------
# Attempt GUI launch only when PyQt6 is available
# ---------------------------------------------------------------------------

try:
    from PyQt6.QtCore import QTimer, QUrl, Qt
    from PyQt6.QtWidgets import (
        QApplication,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QMainWindow,
        QPushButton,
        QStatusBar,
        QVBoxLayout,
        QWidget,
    )
    from PyQt6.QtWebEngineWidgets import QWebEngineView

    _PYQT6_AVAILABLE = True
except ImportError:
    _PYQT6_AVAILABLE = False
    logger.warning("PyQt6 / QWebEngineWidgets not available — GUI will not launch")


# ---------------------------------------------------------------------------
# Default desktop home page
# ---------------------------------------------------------------------------

def ensure_default_desktop() -> str:
    """Return the URL for the default home page, creating the file if absent."""
    home = os.path.join(os.path.dirname(os.path.abspath(__file__)), "desktop_home.html")
    if os.path.exists(home):
        logger.info("Using existing desktop_home.html: %s", home)
        return home

    logger.info("desktop_home.html not found — creating default placeholder")
    html = (
        "<!DOCTYPE html><html><head><meta charset='utf-8'>"
        "<title>AI Desktop Canvas</title></head>"
        "<body style='margin:0;background:#0f172a;color:#e2e8f0;"
        "font-family:system-ui,sans-serif;display:flex;"
        "align-items:center;justify-content:center;height:100vh;'>"
        "<div style='text-align:center'>"
        "<h1 style='color:#00d2ff;font-size:2rem;'>AI Desktop Canvas</h1>"
        "<p>Ready — navigate to any URL using the address bar above.</p>"
        "</div></body></html>"
    )
    try:
        with open(home, "w", encoding="utf-8") as fh:
            fh.write(html)
        logger.info("Created desktop_home.html at: %s", home)
    except OSError as exc:
        logger.warning("Could not write desktop_home.html: %s", exc)
    return home


# ---------------------------------------------------------------------------
# PyQt6 canvas window
# ---------------------------------------------------------------------------

if _PYQT6_AVAILABLE:

    class AIDesktopCanvas(QMainWindow):
        """PyQt6 window that embeds a Chromium browser and writes live bounds to canvas_state.json."""

        DEFAULT_WIDTH = 1260
        DEFAULT_HEIGHT = 800

        def __init__(self, initial_url: str = "about:blank"):
            super().__init__()
            self.setWindowTitle("AI Desktop Canvas")
            self.resize(self.DEFAULT_WIDTH, self.DEFAULT_HEIGHT)

            # Central widget + layout
            central = QWidget()
            self.setCentralWidget(central)
            layout = QVBoxLayout(central)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(0)

            # Navigation bar
            nav_bar = QWidget()
            nav_layout = QHBoxLayout(nav_bar)
            nav_layout.setContentsMargins(4, 4, 4, 4)

            self._url_input = QLineEdit()
            self._url_input.setPlaceholderText("Enter URL and press Enter…")
            self._url_input.returnPressed.connect(self._on_navigate)
            nav_layout.addWidget(self._url_input)

            back_btn = QPushButton("←")
            back_btn.setFixedWidth(30)
            back_btn.clicked.connect(lambda: self._view.back())
            nav_layout.addWidget(back_btn)

            fwd_btn = QPushButton("→")
            fwd_btn.setFixedWidth(30)
            fwd_btn.clicked.connect(lambda: self._view.forward())
            nav_layout.addWidget(fwd_btn)

            layout.addWidget(nav_bar)

            # Web view
            self._view = QWebEngineView()
            layout.addWidget(self._view)

            # Status bar HUD
            self._status_bar = QStatusBar()
            self.setStatusBar(self._status_bar)
            self._bounds_label = QLabel("bounds: …")
            self._status_bar.addPermanentWidget(self._bounds_label)

            # Load initial URL
            self._view.load(QUrl(initial_url))
            self._view.urlChanged.connect(self._on_url_changed)

            # Refresh timer — write state every 1 second
            self._timer = QTimer(self)
            self._timer.timeout.connect(self._write_state)
            self._timer.start(1000)

        # ------------------------------------------------------------------
        def _write_state(self):
            """Write current window geometry to canvas_state.json."""
            try:
                geom = self.geometry()
                pos = self.mapToGlobal(self._view.pos())
                vw = self._view.width()
                vh = self._view.height()
                bounds = [pos.x(), pos.y(), vw, vh]
                state = {
                    "bounds": bounds,
                    "hwnd": int(self.winId()),
                    "timestamp": time.time(),
                }
                with open(CANVAS_STATE_FILE, "w", encoding="utf-8") as fh:
                    json.dump(state, fh)
                self._bounds_label.setText(
                    f"bounds: ({pos.x()},{pos.y()}) {vw}×{vh}"
                )
            except Exception as exc:
                logger.warning("Failed to write canvas_state.json: %s", exc)

        def _on_navigate(self):
            url = self._url_input.text().strip()
            if url and not url.startswith(("http://", "https://", "file://")):
                url = "https://" + url
            if url:
                self._view.load(QUrl(url))

        def _on_url_changed(self, qurl: QUrl):
            self._url_input.setText(qurl.toString())

        # Pass-through move/resize events so state file is always current
        def moveEvent(self, event):
            super().moveEvent(event)
            self._write_state()

        def resizeEvent(self, event):
            super().resizeEvent(event)
            self._write_state()

        def showEvent(self, event):
            super().showEvent(event)
            self._write_state()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    if not _PYQT6_AVAILABLE:
        logger.error("PyQt6 is not installed — cannot launch the canvas window.")
        sys.exit(1)

    url = sys.argv[1] if len(sys.argv) > 1 else None
    if not url:
        home = ensure_default_desktop()
        url = f"file:///{home.replace(os.sep, '/')}"

    app = QApplication(sys.argv)
    app.setApplicationName("AI Desktop Canvas")

    # High-DPI awareness (Qt 6 handles this automatically, but be explicit)
    app.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps, True)

    logger.info("Launching AI Desktop Canvas → %s", url)
    window = AIDesktopCanvas(initial_url=url)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
