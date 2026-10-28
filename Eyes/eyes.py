"""
eyes.py  -  EYES Vision & Screen Grounding Engine
Gives ANY AI the ability to see, understand, and interact with the user's screen.

Features:
- Full screen & region capture (PNG, Base64 thumbnail, file storage)
- OCR text extraction with spatial bounding boxes and word confidence (Tesseract)
- Multi-provider visual description (Ollama LLaVA, OpenAI GPT-4o, Anthropic Claude, Gemini, or OCR fallback)
- High-precision UI element finding (fuzzy text match + OCR coordinates)
- Mouse & Keyboard interactions (click, double click, right click, type, press key, scroll)
- Windows high-DPI scaling awareness
- Standalone CLI interface + Python SDK
"""

import os
import sys
import json
import base64
import io
import time
import shutil
import ctypes
import threading
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, Union, List, Tuple
from contextlib import contextmanager
from PIL import Image


try:
    from .coords import box_center, get_screen_size
    from .diffing import wait_until
    from .observe import build_observation
    from .schema import Observation, UIElement, resolve_element
except (ImportError, ValueError):
    from Eyes.coords import box_center, get_screen_size
    from Eyes.diffing import wait_until
    from Eyes.observe import build_observation
    from Eyes.schema import Observation, UIElement, resolve_element

# Ã¢â€â‚¬Ã¢â€â‚¬ Enable High-DPI Awareness on Windows Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬
if sys.platform == "win32":
    try:
        # 2 = PROCESS_PER_MONITOR_DPI_AWARE
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

# Ã¢â€â‚¬Ã¢â€â‚¬ Paths & Configuration Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬
EYES_DIR = Path(__file__).parent.resolve()
SHOTS_DIR = EYES_DIR / "screenshots"
SHOTS_DIR.mkdir(parents=True, exist_ok=True)

TESSERACT_PATHS = [
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    r"C:\Users\Lenovo\AppData\Local\Programs\Tesseract-OCR\tesseract.exe",
    os.path.expanduser(r"~\AppData\Local\Programs\Tesseract-OCR\tesseract.exe"),
]

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")
VISION_MODEL = os.getenv("VISION_MODEL", "llava:7b")

# Ã¢â€â‚¬Ã¢â€â‚¬ Canvas Bounding & Ephemeral Lifecycle Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬
_ACTIVE_CANVAS_REGION: Optional[Tuple[int, int, int, int]] = None
_ACTIVE_TASK_SESSION: Optional["TaskSession"] = None
_SESSION_LOCK = threading.Lock()


class TaskSession:
    """Manages ephemeral screenshot lifecycle during task execution. All screenshots auto-delete on completion."""

    def __init__(self, task_name: str = "task"):
        self.task_name = task_name
        self.screenshots: List[str] = []
        self.is_active = True
        self.started_at = time.time()
        self._lock = threading.Lock()

    def add_screenshot(self, path: str):
        if not path:
            return
        with self._lock:
            if path not in self.screenshots:
                self.screenshots.append(path)

    def cleanup(self) -> int:
        """Purge all temporary screenshots created during this task execution."""
        with self._lock:
            deleted_count = 0
            for path in list(self.screenshots):
                try:
                    if os.path.exists(path):
                        os.remove(path)
                        deleted_count += 1
                except Exception:
                    pass
            self.screenshots.clear()
            self.is_active = False
            return deleted_count


def set_canvas_region(region: Optional[Tuple[int, int, int, int]]):
    """Set the active canvas bounding box (x, y, width, height) to restrict all Eyes operations strictly inside it."""
    global _ACTIVE_CANVAS_REGION
    with _SESSION_LOCK:
        _ACTIVE_CANVAS_REGION = region


def get_canvas_region() -> Optional[Tuple[int, int, int, int]]:
    """Get the currently active canvas bounding box, if any."""
    with _SESSION_LOCK:
        return _ACTIVE_CANVAS_REGION


def start_task(task_name: str = "task") -> TaskSession:
    """Start an ephemeral task session. All screenshots created during this task are deleted upon end_task()."""
    global _ACTIVE_TASK_SESSION
    with _SESSION_LOCK:
        if _ACTIVE_TASK_SESSION:
            _ACTIVE_TASK_SESSION.cleanup()
        _ACTIVE_TASK_SESSION = TaskSession(task_name)
        return _ACTIVE_TASK_SESSION


def end_task() -> int:
    """End the current task session and delete all screenshots created during it."""
    global _ACTIVE_TASK_SESSION
    with _SESSION_LOCK:
        if _ACTIVE_TASK_SESSION:
            deleted = _ACTIVE_TASK_SESSION.cleanup()
            _ACTIVE_TASK_SESSION = None
            return deleted
        return 0


@contextmanager
def task_session(task_name: str = "task"):
    """Context manager for ephemeral screenshot lifecycle."""
    session = start_task(task_name)
    try:
        yield session
    finally:
        end_task()


# Ã¢â€â‚¬Ã¢â€â‚¬ Tesseract Path Detection Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬
def _find_tesseract() -> Optional[str]:
    for p in TESSERACT_PATHS:
        if os.path.exists(p):
            return p
    found = shutil.which("tesseract")
    return found


# Ã¢â€â‚¬Ã¢â€â‚¬ Lazy Dependency Loader Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬
def _get_deps():
    try:
        import pyautogui
        import pytesseract
        from PIL import Image
        import cv2
        import numpy as np
        import requests

        # PyAutoGUI fail-safe settings
        pyautogui.FAILSAFE = True
        pyautogui.PAUSE = 0.1

        tess = _find_tesseract()
        if tess:
            pytesseract.pytesseract.tesseract_cmd = tess

        return pyautogui, pytesseract, Image, cv2, np, requests
    except ImportError as e:
        raise ImportError(
            f"Missing required dependency: {e}. "
            f"Run: pip install pyautogui pytesseract pillow opencv-python requests"
        )


def _image_to_base64(image, max_size: Optional[Tuple[int, int]] = (1280, 720)) -> str:
    """Convert a PIL Image to JPEG base64 string, optionally resized for low latency."""
    img = image.copy()
    if max_size and (img.width > max_size[0] or img.height > max_size[1]):
        img.thumbnail(max_size)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def _ensure_input_desktop():
    """Ensure current thread is attached to Windows input desktop for live screen access."""
    if sys.platform == "win32":
        try:
            user32 = ctypes.windll.user32
            hdesk = user32.OpenInputDesktop(0, False, 0x01FF)
            if hdesk:
                user32.SetThreadDesktop(hdesk)
        except Exception:
            pass


def _win32_gdi_grab(region: Optional[Tuple[int, int, int, int]] = None) -> Image.Image:
    """
    Direct Windows GDI BitBlt screen grab.
    Uses SRCCOPY (0x00CC0020) without CAPTUREBLT to guarantee success in background/subprocess contexts.
    """
    from ctypes import wintypes

    _ensure_input_desktop()
    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32

    full_w = user32.GetSystemMetrics(0)
    full_h = user32.GetSystemMetrics(1)

    if region:
        rx, ry, rw, rh = region
        x = max(0, min(rx, full_w - 1))
        y = max(0, min(ry, full_h - 1))
        w = max(1, min(rw, full_w - x))
        h = max(1, min(rh, full_h - y))
    else:
        x, y, w, h = 0, 0, full_w, full_h

    hdc = user32.GetDC(0)
    memdc = None
    bmp = None
    old_bmp = None
    try:
        memdc = gdi32.CreateCompatibleDC(hdc)
        bmp = gdi32.CreateCompatibleBitmap(hdc, w, h)
        old_bmp = gdi32.SelectObject(memdc, bmp)

        # 0x00CC0020 is SRCCOPY
        gdi32.BitBlt(memdc, 0, 0, w, h, hdc, x, y, 0x00CC0020)

        class BITMAPINFOHEADER(ctypes.Structure):
            _fields_ = [
                ("biSize", wintypes.DWORD),
                ("biWidth", wintypes.LONG),
                ("biHeight", wintypes.LONG),
                ("biPlanes", wintypes.WORD),
                ("biBitCount", wintypes.WORD),
                ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD),
                ("biXPelsPerMeter", wintypes.LONG),
                ("biYPelsPerMeter", wintypes.LONG),
                ("biClrUsed", wintypes.DWORD),
                ("biClrImportant", wintypes.DWORD),
            ]

        bmi = BITMAPINFOHEADER()
        bmi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmi.biWidth = w
        bmi.biHeight = -h  # top-down DIB
        bmi.biPlanes = 1
        bmi.biBitCount = 32
        bmi.biCompression = 0

        buf = ctypes.create_string_buffer(w * h * 4)
        gdi32.GetDIBits(memdc, bmp, 0, h, buf, ctypes.byref(bmi), 0)
        img = Image.frombuffer("RGBA", (w, h), bytes(buf), "raw", "BGRA", 0, 1).convert("RGB")
        return img
    finally:
        if memdc and old_bmp:
            try:
                gdi32.SelectObject(memdc, old_bmp)
            except Exception:
                pass
        if bmp:
            try:
                gdi32.DeleteObject(bmp)
            except Exception:
                pass
        if memdc:
            try:
                gdi32.DeleteDC(memdc)
            except Exception:
                pass
        if hdc:
            try:
                user32.ReleaseDC(0, hdc)
            except Exception:
                pass


def _grab_screen(region: Optional[Tuple[int, int, int, int]] = None) -> Image.Image:
    """Multi-tiered screen grabber that works across all execution contexts."""
    _ensure_input_desktop()

    # Priority 1: PIL ImageGrab (with active thread desktop attached)
    try:
        from PIL import ImageGrab
        bbox = None
        if region:
            bbox = (region[0], region[1], region[0] + region[2], region[1] + region[3])
        img = ImageGrab.grab(bbox=bbox)
        # Check if non-empty
        extrema = img.getextrema()
        if extrema != ((0, 0), (0, 0), (0, 0)):
            return img
    except Exception:
        pass

    # Priority 2: Windows GDI
    if sys.platform == "win32":
        try:
            return _win32_gdi_grab(region)
        except Exception:
            pass

    # Priority 3: PyAutoGUI screenshot
    try:
        pyautogui, _, _, _, _, _ = _get_deps()
        shot = pyautogui.screenshot(region=region)
        if isinstance(shot, Image.Image):
            return shot
    except Exception:
        pass

    # Final fallback
    from PIL import ImageGrab
    return ImageGrab.grab()


# Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬
# 1. SCREEN CAPTURE
# Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬

def capture(region: Optional[Tuple[int, int, int, int]] = None, save: bool = True, include_base64: bool = False) -> Dict[str, Any]:
    """
    Capture the full screen or a bounding box region.
    
    Args:
        region: Tuple of (x, y, width, height) or None for primary display.
        save: Save image to screenshots/ directory.
        include_base64: Include base64 JPEG representation.
        
    Returns:
        { "success": bool, "path": str, "width": int, "height": int, "base64": str, "error": str | None }
    """
    try:
        active_region = region if region is not None else _ACTIVE_CANVAS_REGION
        screenshot = _grab_screen(region=active_region)
        path = None
        if save:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:19]
            path = str(SHOTS_DIR / f"screen_{ts}.png")
            screenshot.save(path)
            if _ACTIVE_TASK_SESSION:
                _ACTIVE_TASK_SESSION.add_screenshot(path)

        b64 = _image_to_base64(screenshot) if include_base64 else None

        return {
            "success": True,
            "path": path,
            "width": screenshot.width,
            "height": screenshot.height,
            "base64": b64,
            "region": active_region,
            "error": None
        }
    except Exception as e:
        return {
            "success": False,
            "path": None,
            "width": 0,
            "height": 0,
            "base64": None,
            "region": region,
            "error": str(e)
        }


# Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬
# 2. OCR (READ TEXT)
# Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬

def read_text(region: Optional[Tuple[int, int, int, int]] = None, detailed: bool = False) -> Dict[str, Any]:
    """
    Extract text on screen using OCR.
    
    Args:
        region: (x, y, width, height) or None for full screen.
        detailed: If True, returns word-level bounding boxes and confidence scores.
        
    Returns:
        { "success": bool, "text": str, "elements": list, "error": str | None }
    """
    try:
        active_region = region if region is not None else _ACTIVE_CANVAS_REGION
        pyautogui, pytesseract, _, _, _, _ = _get_deps()
        tess = _find_tesseract()
        if not tess:
            return {
                "success": False,
                "text": "",
                "elements": [],
                "error": "Tesseract OCR binary not found. Please install Tesseract-OCR."
            }
        pytesseract.pytesseract.tesseract_cmd = tess

        # Capture once in memory and use that exact frame for OCR. The previous
        # path captured the screen via capture() and then immediately captured it
        # again, wasting time and potentially transcribing a different frame.
        try:
            screenshot = _grab_screen(region=active_region)
        except Exception as capture_error:
            return {
                "success": False,
                "text": "",
                "elements": [],
                "error": f"Screen capture failed: {capture_error}",
            }

        if not detailed:
            raw_text = pytesseract.image_to_string(screenshot)
            if isinstance(raw_text, dict):
                text = str(raw_text.get("text", "")).strip()
            elif isinstance(raw_text, (bytes, bytearray)):
                text = raw_text.decode("utf-8", errors="replace").strip()
            elif isinstance(raw_text, str):
                text = raw_text.strip()
            else:
                text = str(raw_text or "").strip()

            return {
                "success": True,
                "text": text if text else "(No visible text detected on screen)",
                "elements": [],
                "error": None
            }

        # Word-level bounding boxes
        data = pytesseract.image_to_data(screenshot, output_type=pytesseract.Output.DICT)
        elements = []
        full_text_parts = []
        n_boxes = len(data["text"])

        offset_x = active_region[0] if active_region else 0
        offset_y = active_region[1] if active_region else 0

        for i in range(n_boxes):
            word = data["text"][i].strip()
            conf = int(data["conf"][i])
            if word and conf > 25:
                x = data["left"][i] + offset_x
                y = data["top"][i] + offset_y
                w = data["width"][i]
                h = data["height"][i]
                full_text_parts.append(word)
                elements.append({
                    "text": word,
                    "confidence": conf,
                    "box": {"x": x, "y": y, "width": w, "height": h},
                    "center": {"x": x + w // 2, "y": y + h // 2}
                })

        return {
            "success": True,
            "text": " ".join(full_text_parts),
            "elements": elements,
            "error": None
        }
    except Exception as e:
        return {"success": False, "text": "", "elements": [], "error": str(e)}


def _column_label(index: int) -> str:
    """Convert a zero-based column index to Excel-style labels (A, B, ..., AA)."""
    label = ""
    index += 1
    while index:
        index, remainder = divmod(index - 1, 26)
        label = chr(65 + remainder) + label
    return label


def screen_map(
    columns: int = 12,
    rows: int = 8,
    region: Optional[Tuple[int, int, int, int]] = None,
    min_confidence: int = 25,
) -> Dict[str, Any]:
    """Create a spatial, cell-based transcription of the current screen.

    OCR word boxes are assigned to every grid cell they touch.  The returned
    cell center is only a spatial reference; element centers and bounding
    boxes remain available for precise interaction.
    """
    if columns < 1 or rows < 1 or columns > 52 or rows > 100:
        return {"success": False, "error": "columns must be 1-52 and rows must be 1-100"}

    ocr = read_text(region=region, detailed=True)
    if not ocr.get("success"):
        return {"success": False, "error": ocr.get("error", "OCR failed"), "elements": [], "cells": []}

    active_region = region if region is not None else _ACTIVE_CANVAS_REGION
    if active_region:
        width, height = active_region[2], active_region[3]
        origin_x, origin_y = active_region[0], active_region[1]
    else:
        width, height = _grab_screen().size
        origin_x, origin_y = 0, 0

    cell_w = width / columns
    cell_h = height / rows
    cells = []
    for row in range(rows):
        for col in range(columns):
            name = f"{_column_label(col)}{row + 1}"
            left = round(origin_x + col * cell_w)
            top = round(origin_y + row * cell_h)
            right = round(origin_x + (col + 1) * cell_w)
            bottom = round(origin_y + (row + 1) * cell_h)
            cells.append({
                "cell": name,
                "row": row + 1,
                "column": col + 1,
                "box": {"left": left, "top": top, "width": right - left, "height": bottom - top},
                "center": {"x": (left + right) // 2, "y": (top + bottom) // 2},
                "corners": {
                    "top_left": {"x": left, "y": top},
                    "top_right": {"x": right, "y": top},
                    "bottom_left": {"x": left, "y": bottom},
                    "bottom_right": {"x": right, "y": bottom},
                },
                "elements": [],
            })

    mapped_elements = []
    for index, element in enumerate(ocr.get("elements", []), start=1):
        if element.get("confidence", 0) < min_confidence:
            continue
        box = element["box"]
        center = element["center"]
        # Coordinates are absolute when a region is supplied by read_text.
        local_x = center["x"] - origin_x
        local_y = center["y"] - origin_y
        col = max(0, min(columns - 1, int(local_x / cell_w)))
        row = max(0, min(rows - 1, int(local_y / cell_h)))
        cell_name = f"{_column_label(col)}{row + 1}"
        mapped = dict(element)
        mapped["id"] = f"e{index}"
        mapped["cell"] = cell_name
        mapped["corners"] = {
            "top_left": {"x": box["x"], "y": box["y"]},
            "top_right": {"x": box["x"] + box["width"], "y": box["y"]},
            "bottom_left": {"x": box["x"], "y": box["y"] + box["height"]},
            "bottom_right": {"x": box["x"] + box["width"], "y": box["y"] + box["height"]},
        }
        mapped_elements.append(mapped)
        cells[row * columns + col]["elements"].append(mapped["id"])

    by_id = {element["id"]: element for element in mapped_elements}
    transcription = []
    for cell in cells:
        if cell["elements"]:
            entries = [by_id[item] for item in cell["elements"]]
            text = " ".join(item["text"] for item in entries)
            c = cell["corners"]
            transcription.append(
                f"[{cell['cell']} ({c['top_left']['x']},{c['top_left']['y']} -> {c['bottom_right']['x']},{c['bottom_right']['y']})] {text}"
            )

    return {
        "success": True,
        "grid": {"columns": columns, "rows": rows, "width": width, "height": height, "region": active_region},
        "transcription": "\n".join(transcription) or "(No visible text detected on screen)",
        "elements": mapped_elements,
        "cells": cells,
        "error": None,
    }


# Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬
# 3. FIND ON SCREEN (VISUAL GROUNDING)
# Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬

def find_on_screen(target: str, min_confidence: int = 30) -> Dict[str, Any]:
    """
    Find text or label on screen with bounding box and center coordinates.
    Supports single words or multi-word phrases.
    """
    try:
        pyautogui, pytesseract, _, _, _, _ = _get_deps()
        tess = _find_tesseract()
        if not tess:
            return {"success": False, "result": None, "error": "Tesseract OCR binary not found."}
        pytesseract.pytesseract.tesseract_cmd = tess

        active_region = _ACTIVE_CANVAS_REGION
        screenshot = _grab_screen(region=active_region)
        data = pytesseract.image_to_data(screenshot, output_type=pytesseract.Output.DICT)

        offset_x = active_region[0] if active_region else 0
        offset_y = active_region[1] if active_region else 0

        target_clean = target.strip().lower()
        words = target_clean.split()

        matches = []
        n_boxes = len(data["text"])

        # Check single-word and exact substring matches
        for i in range(n_boxes):
            text = data["text"][i].strip()
            conf = int(data["conf"][i])
            if conf >= min_confidence and text:
                if target_clean in text.lower() or any(w in text.lower() for w in words):
                    x = data["left"][i] + offset_x
                    y = data["top"][i] + offset_y
                    w = data["width"][i]
                    h = data["height"][i]
                    matches.append({
                        "matched_text": text,
                        "confidence": conf,
                        "x": x + w // 2,
                        "y": y + h // 2,
                        "box": {"left": x, "top": y, "width": w, "height": h}
                    })

        if matches:
            # Sort by best match (exact matches first, then highest confidence)
            exact = [m for m in matches if target_clean == m["matched_text"].lower()]
            best = exact[0] if exact else max(matches, key=lambda m: m["confidence"])

            return {
                "success": True,
                "found": True,
                "target": target,
                "x": best["x"],
                "y": best["y"],
                "matched_text": best["matched_text"],
                "confidence": best["confidence"],
                "box": best["box"],
                "all_matches": matches[:5],
                "error": None
            }

        return {
            "success": True,
            "found": False,
            "target": target,
            "x": None,
            "y": None,
            "matched_text": None,
            "confidence": 0,
            "all_matches": [],
            "error": f"Target '{target}' not found on screen via OCR."
        }
    except Exception as e:
        return {"success": False, "found": False, "error": str(e)}


# Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬
# 4. DESCRIBE SCREEN (MULTI-MODAL VISION)
# Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬

def describe(prompt: Optional[str] = None, region: Optional[Tuple[int, int, int, int]] = None) -> Dict[str, Any]:
    """
    Send the screen to a Vision LLM for visual understanding.
    Checks in order: Ollama (LLaVA), OpenAI GPT-4o, Anthropic Claude, or OCR fallback.
    """
    try:
        active_region = region if region is not None else _ACTIVE_CANVAS_REGION
        pyautogui, _, Image, _, _, requests = _get_deps()
        screenshot = _grab_screen(region=active_region)
        b64_img = _image_to_base64(screenshot)

        q = prompt or (
            "Describe the visible screen accurately. "
            "List active application windows, main UI components, buttons, menus, and any important notifications."
        )

        # 1. Try local Ollama first
        try:
            payload = {
                "model": VISION_MODEL,
                "prompt": q,
                "images": [b64_img],
                "stream": False,
            }
            r = requests.post(OLLAMA_URL, json=payload, timeout=25)
            if r.status_code == 200:
                res_text = r.json().get("response", "").strip()
                if res_text:
                    return {
                        "success": True,
                        "provider": f"Ollama ({VISION_MODEL})",
                        "description": res_text,
                        "error": None
                    }
        except Exception:
            pass

        # 2. Try OpenAI API if key present
        openai_key = os.getenv("OPENAI_API_KEY")
        if openai_key:
            try:
                headers = {"Authorization": f"Bearer {openai_key}", "Content-Type": "application/json"}
                payload = {
                    "model": "gpt-4o-mini",
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": q},
                                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_img}"}}
                            ]
                        }
                    ],
                    "max_tokens": 500
                }
                r = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload, timeout=30)
                if r.status_code == 200:
                    desc = r.json()["choices"][0]["message"]["content"].strip()
                    return {"success": True, "provider": "OpenAI (gpt-4o-mini)", "description": desc, "error": None}
            except Exception:
                pass

        # 3. Fallback: Structural OCR Summary
        ocr_res = read_text(region=region)
        ocr_snippet = ocr_res["text"][:1000] if ocr_res["success"] else "No OCR text"

        return {
            "success": True,
            "provider": "OCR Structural Analysis (Vision Model Offline)",
            "description": (
                f"Vision model service is offline at {OLLAMA_URL}. "
                f"Screen OCR extracted text summary:\n{ocr_snippet}"
            ),
            "error": None
        }
    except Exception as e:
        return {"success": False, "description": "", "error": str(e)}


# Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬
# 5. MOUSE & KEYBOARD INTERACTIONS
# Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬

def click(x: Optional[int] = None, y: Optional[int] = None, target: Optional[str] = None, click_type: str = "left") -> Dict[str, Any]:
    """
    Click at specific (x, y) coordinates or find and click a text label.
    """
    try:
        pyautogui, _, _, _, _, _ = _get_deps()

        target_x, target_y = x, y

        if target_x is None or target_y is None:
            if not target:
                return {"success": False, "error": "Either (x, y) or target text must be provided."}
            find_res = find_on_screen(target)
            if not find_res.get("found"):
                return {"success": False, "error": f"Element '{target}' not found on screen to click."}
            target_x = find_res["x"]
            target_y = find_res["y"]

        # Bounds check
        screen_w, screen_h = get_screen_size()
        if not (0 <= target_x <= screen_w and 0 <= target_y <= screen_h):
            return {"success": False, "error": f"Coordinates ({target_x}, {target_y}) out of screen bounds ({screen_w}x{screen_h})."}

        pyautogui.moveTo(target_x, target_y, duration=0.2)
        if click_type == "double":
            pyautogui.doubleClick(target_x, target_y)
        elif click_type == "right":
            pyautogui.rightClick(target_x, target_y)
        else:
            pyautogui.click(target_x, target_y)

        return {
            "success": True,
            "action": f"Clicked ({click_type}) at ({target_x}, {target_y})",
            "x": target_x,
            "y": target_y,
            "error": None
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def type_text(text: str, interval: float = 0.02, press_enter: bool = False) -> Dict[str, Any]:
    """
    Type text into the currently focused window.
    """
    try:
        pyautogui, _, _, _, _, _ = _get_deps()
        pyautogui.write(text, interval=interval)
        if press_enter:
            pyautogui.press("enter")
        return {"success": True, "action": f"Typed '{text}'", "error": None}
    except Exception as e:
        return {"success": False, "error": str(e)}


def press_key(key: Union[str, List[str]]) -> Dict[str, Any]:
    """
    Press a single key or key combination (e.g. 'enter', ['ctrl', 'c'], ['alt', 'tab']).
    """
    try:
        pyautogui, _, _, _, _, _ = _get_deps()
        if isinstance(key, list):
            pyautogui.hotkey(*key)
            action = f"Hotkey {key}"
        else:
            pyautogui.press(key)
            action = f"Pressed {key}"
        return {"success": True, "action": action, "error": None}
    except Exception as e:
        return {"success": False, "error": str(e)}


def scroll(clicks: int = -3) -> Dict[str, Any]:
    """
    Scroll mouse wheel (negative for down, positive for up).
    """
    try:
        pyautogui, _, _, _, _, _ = _get_deps()
        pyautogui.scroll(clicks)
        return {"success": True, "action": f"Scrolled {clicks} clicks", "error": None}
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_screen_info() -> Dict[str, Any]:
    """
    Returns screen resolution, cursor position, and display details.
    """
    try:
        pyautogui, _, _, _, _, _ = _get_deps()
        w, h = pyautogui.size()
        cur_x, cur_y = pyautogui.position()
        return {
            "success": True,
            "width": w,
            "height": h,
            "cursor": {"x": cur_x, "y": cur_y},
            "error": None
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


# Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬
# 6. UNIFIED OBSERVATION & ELEMENT RESOLUTION PIPELINE
# Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬

def observe(
    save_annotated: bool = True,
    max_elements: int = 100,
    mode: str = "balanced",
    compact: bool = False,
    save_raw: bool = True,
) -> Dict[str, Any]:
    """Capture screen and build a unified observation with numbered UI elements.
    
    Synthesizes Windows UI Automation, tuned OCR, and computer vision cues.
    All elements are assigned sequential IDs for deterministic grounding.

    Args:
        save_annotated: Save and mark visual Set-of-Marks badges.
        max_elements: Maximum elements to retain in the observation.
        mode: Perception mode ('fast', 'balanced', 'deep').
        compact: If True, serialize only concise fields for LLM token savings.
        save_raw: If False, skip saving raw/annotated screenshots to disk.
                  Use for transient observations (verification, polling).
    """
    try:
        active_region = _ACTIVE_CANVAS_REGION
        t_cap = time.perf_counter()
        screenshot = _grab_screen(region=active_region)
        capture_burst_ms = round((time.perf_counter() - t_cap) * 1000.0, 2)
        offset = (active_region[0], active_region[1]) if active_region else (0, 0)
        active_win = ""
        try:
            import win32gui
            hwnd = win32gui.GetForegroundWindow()
            if hwnd and win32gui.IsWindow(hwnd):
                active_win = win32gui.GetWindowText(hwnd).strip()
        except Exception:
            pass

        obs = build_observation(
            screen_image=screenshot,
            active_window_title=active_win or "Active Desktop",
            save_annotated=save_annotated if save_raw else False,
            screenshots_dir=str(SHOTS_DIR) if save_raw else None,
            max_elements=max_elements,
            mode=mode,
            offset=offset,
            save_raw=save_raw,
        )

        global _ACTIVE_TASK_SESSION
        if _ACTIVE_TASK_SESSION:
            if obs.image_path:
                _ACTIVE_TASK_SESSION.add_screenshot(obs.image_path)
            if obs.annotated_image_path:
                _ACTIVE_TASK_SESSION.add_screenshot(obs.annotated_image_path)

        res = obs.to_dict(compact=compact)
        if "timings" in res and isinstance(res["timings"], dict):
            res["timings"]["capture_burst_ms"] = capture_burst_ms
            res["timings"]["capture_ms"] = capture_burst_ms
            total_b = round(res["timings"].get("total_burst_ms", 0.0) + capture_burst_ms, 2)
            res["timings"]["total_burst_ms"] = total_b
            res["timings"]["total_ms"] = total_b
        res["success"] = True
        return res
    except Exception as e:
        return {"success": False, "error": str(e), "elements": []}


def zoom(
    region: Optional[List[int]] = None,
    element_id: Optional[int] = None,
    scale: float = 3.0,
) -> Dict[str, Any]:
    """Crop and zoom into a bounding box or element ID with high-resolution OCR."""
    box = region
    if element_id is not None:
        el = resolve_element(element_id)
        if el:
            box = el.box
        else:
            return {"success": False, "error": f"Element ID {element_id} not found in current observation"}

    if not box:
        return {"success": False, "error": "Either region [x1, y1, x2, y2] or element_id must be provided"}

    x1, y1, x2, y2 = box
    w = max(1, x2 - x1)
    h = max(1, y2 - y1)
    crop_region = (x1, y1, w, h)

    cropped = _grab_screen(region=crop_region)
    try:
        from .ocr import extract_ocr_elements
    except ImportError:
        from ocr import extract_ocr_elements

    elements = extract_ocr_elements(cropped, scale=scale, offset=(x1, y1))

    text = ""
    try:
        pyautogui, pytesseract, _, _, _, _ = _get_deps()
        tess = _find_tesseract()
        if tess:
            pytesseract.pytesseract.tesseract_cmd = tess
        raw_text = pytesseract.image_to_string(cropped)
        if isinstance(raw_text, dict):
            text = str(raw_text.get("text", "")).strip()
        elif isinstance(raw_text, (bytes, bytearray)):
            text = raw_text.decode("utf-8", errors="replace").strip()
        elif isinstance(raw_text, str):
            text = raw_text.strip()
        else:
            text = str(raw_text or "").strip()
    except Exception:
        pass

    if not text and elements:
        text = " ".join(el.name for el in elements if el.name).strip()

    return {
        "success": True,
        "region": box,
        "text": text,
        "elements": [el.to_dict() for el in elements],
    }


def wait_for_text(target: str, timeout_s: float = 5.0) -> Dict[str, Any]:
    """Poll the screen until target text appears, returning the matched element."""
    found_element = None
    target_lower = target.strip().lower()

    def check():
        nonlocal found_element
        obs_dict = observe(save_annotated=False)
        if not obs_dict.get("success"):
            return False
        for el in obs_dict.get("elements", []):
            if target_lower in el.get("name", "").lower():
                found_element = el
                return True
        return False

    success = wait_until(check, timeout_s=timeout_s, poll_interval_s=0.25)
    return {
        "success": success,
        "target": target,
        "element": found_element,
        "timed_out": not success,
    }


def resolve_element_center(
    element_id: int,
    observation_id: Optional[str] = None,
) -> Optional[Tuple[int, int]]:
    """Resolve element ID to physical center coordinates (cx, cy) from current or targeted observation."""
    el = resolve_element(element_id, observation_id=observation_id)
    if el:
        return el.center
    return None


def ground_target(
    instruction: str,
    min_confidence: float = 0.4,
) -> Dict[str, Any]:
    """Locate candidate UI element coordinates matching a natural language instruction."""
    try:
        from .visual_grounding import get_default_grounder
    except ImportError:
        try:
            from visual_grounding import get_default_grounder
        except ImportError:
            return {"success": False, "candidates": [], "error": "Visual grounding subsystem not available"}

    active_region = _ACTIVE_CANVAS_REGION
    shot = _grab_screen(region=active_region)
    offset = (active_region[0], active_region[1]) if active_region else (0, 0)

    grounder = get_default_grounder()
    candidates = grounder.ground_target(shot, instruction, offset=offset, min_confidence=min_confidence)
    return {
        "success": True,
        "instruction": instruction,
        "candidates": [c.to_dict() for c in candidates],
        "best_candidate": candidates[0].to_dict() if candidates else None,
        "count": len(candidates),
    }



# Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬
# 7. STANDALONE CLI INTERFACE
# Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬


def main():
    import argparse
    from prompt_enhancer import PromptEnhancer

    parser = argparse.ArgumentParser(description="EYES - Vision & Screen Grounding Engine for AI")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Capture
    p_cap = subparsers.add_parser("capture", help="Take a screenshot")
    p_cap.add_argument("--save", action="store_true", default=True, help="Save to screenshots folder")

    # OCR
    p_ocr = subparsers.add_parser("ocr", help="Extract text via OCR")
    p_ocr.add_argument("--detailed", action="store_true", help="Include word bounding boxes")

    # Spatial map
    p_map = subparsers.add_parser("map", help="Create a cell-based spatial screen transcription")
    p_map.add_argument("--columns", type=int, default=12)
    p_map.add_argument("--rows", type=int, default=8)
    p_map.add_argument("--min-confidence", type=int, default=25)

    # Find
    p_find = subparsers.add_parser("find", help="Find element or text coordinates")
    p_find.add_argument("target", type=str, help="Text to search for")

    # Click
    p_click = subparsers.add_parser("click", help="Click at coordinates or text")
    p_click.add_argument("--x", type=int, default=None)
    p_click.add_argument("--y", type=int, default=None)
    p_click.add_argument("--target", type=str, default=None)
    p_click.add_argument("--type", type=str, default="left", choices=["left", "right", "double"])

    # Type
    p_type = subparsers.add_parser("type", help="Type text")
    p_type.add_argument("text", type=str)
    p_type.add_argument("--enter", action="store_true", help="Press enter after typing")

    # Describe
    p_desc = subparsers.add_parser("describe", help="Vision model screen description")
    p_desc.add_argument("--prompt", type=str, default=None)

    # Info
    subparsers.add_parser("info", help="Get screen resolution & cursor position")

    # Enhance Prompt
    p_enh = subparsers.add_parser("enhance-prompt", help="Enhance a raw vision task prompt")
    p_enh.add_argument("task", type=str, help="Raw user task description")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    if args.command == "capture":
        res = capture(save=args.save)
        print(json.dumps(res, indent=2))
    elif args.command == "ocr":
        res = read_text(detailed=args.detailed)
        print(json.dumps(res, indent=2))
    elif args.command == "map":
        res = screen_map(columns=args.columns, rows=args.rows, min_confidence=args.min_confidence)
        print(json.dumps(res, indent=2))
    elif args.command == "find":
        res = find_on_screen(args.target)
        print(json.dumps(res, indent=2))
    elif args.command == "click":
        res = click(x=args.x, y=args.y, target=args.target, click_type=args.type)
        print(json.dumps(res, indent=2))
    elif args.command == "type":
        res = type_text(args.text, press_enter=args.enter)
        print(json.dumps(res, indent=2))
    elif args.command == "describe":
        res = describe(prompt=args.prompt)
        print(json.dumps(res, indent=2))
    elif args.command == "info":
        res = get_screen_info()
        print(json.dumps(res, indent=2))
    elif args.command == "enhance-prompt":
        enhancer = PromptEnhancer()
        res = enhancer.enhance_task_prompt(args.task)
        print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()


