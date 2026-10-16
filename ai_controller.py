"""ai_controller.py - AI Controller for Desktop Canvas, Strict Bounding & Ephemeral Storage.

Binds Eyes and Hands exclusively to the AI Desktop Canvas viewport:
- Automatic coordinate synchronization with canvas_desktop.py.
- Strict spatial clamping: All screenshots, OCR transcriptions, clicks, and scrolls happen ONLY inside the canvas.
- Ephemeral lifecycle: All screenshots captured during a task are tracked in memory and automatically purged from disk upon task completion.
"""

import json
import os
import sys
import time
from contextlib import contextmanager
from typing import Any, Dict, Optional, Tuple

# Ensure Eyes and Hands are importable
sys.path.extend([
    os.path.join(os.path.dirname(__file__), "Eyes"),
    os.path.join(os.path.dirname(__file__), "Hands"),
])

import eyes
from agent_hands.engine import TypingEngine
from agent_hands.keyboard import fast_paste, press_single_key
import agent_hands.mouse as hands_mouse
from agent_hands.windows import focus_window

from canvas_desktop import CANVAS_STATE_FILE, get_canvas_bounds


class CanvasAIController:
    """Central AI Controller orchestrating Eyes & Hands strictly within the AI Desktop Canvas."""

    def __init__(self):
        self.active_task: Optional[str] = None
        self.session: Optional[eyes.TaskSession] = None
        self.bounds: Optional[Tuple[int, int, int, int]] = None
        self.sync_canvas_bounds()

    def sync_canvas_bounds(self) -> Optional[Tuple[int, int, int, int]]:
        """Read latest viewport boundaries from canvas_desktop and bind Eyes and Hands."""
        bounds = get_canvas_bounds()
        if bounds:
            self.bounds = bounds
            eyes.set_canvas_region(bounds)
            hands_mouse.set_canvas_bounds(bounds)
        return bounds

    @contextmanager
    def task(self, task_name: str = "ai_task"):
        """Context manager guaranteeing all task screenshots are strictly ephemeral and auto-deleted."""
        self.sync_canvas_bounds()
        self.active_task = task_name
        self.session = eyes.start_task(task_name)
        print(f"\n[AI Controller] [TASK START] Started Task: '{task_name}' (Ephemeral Storage Active)")
        try:
            yield self
        finally:
            deleted = eyes.end_task()
            print(f"[AI Controller] [CLEANUP] Task '{task_name}' Completed. Purged {deleted} ephemeral screenshot(s) from disk.\n")
            self.active_task = None
            self.session = None

    # ── EYES (Perception bounded strictly to canvas) ─────────────────────────

    def capture(self, save: bool = True) -> Dict[str, Any]:
        """Capture screenshot ONLY within the canvas viewport."""
        self.sync_canvas_bounds()
        return eyes.capture(region=self.bounds, save=save)

    def transcribe(self, detailed: bool = False) -> Dict[str, Any]:
        """OCR extract text ONLY within the canvas viewport."""
        self.sync_canvas_bounds()
        return eyes.read_text(region=self.bounds, detailed=detailed)

    def find_on_canvas(self, target: str) -> Dict[str, Any]:
        """Locate element/text specifically inside the canvas viewport."""
        self.sync_canvas_bounds()
        return eyes.find_on_screen(target)

    # ── HANDS (Actions clamped strictly to canvas) ───────────────────────────

    def focus(self) -> bool:
        """Bring the AI Canvas window to the foreground."""
        return focus_window("AI Desktop Workspace")

    def click(
        self,
        x: Optional[int] = None,
        y: Optional[int] = None,
        button: str = "left",
        clicks: int = 1,
    ) -> Dict[str, Any]:
        """Click strictly within the canvas viewport."""
        self.sync_canvas_bounds()
        return hands_mouse.click(x=x, y=y, button=button, clicks=clicks)

    def double_click(self, x: Optional[int] = None, y: Optional[int] = None) -> Dict[str, Any]:
        """Double click within the canvas viewport."""
        return self.click(x=x, y=y, button="left", clicks=2)

    def scroll(self, amount: int, x: Optional[int] = None, y: Optional[int] = None, smooth: bool = True) -> Dict[str, Any]:
        """Scroll mouse wheel strictly within the canvas viewport."""
        self.sync_canvas_bounds()
        return hands_mouse.scroll(clicks=amount, x=x, y=y, smooth=smooth)

    def type_text(self, text: str, profile: str = "natural", typos: bool = False) -> Dict[str, Any]:
        """Type text into the canvas using natural human cadence."""
        engine = TypingEngine(profile=profile)
        return engine.type_text(text=text, introduce_typos=typos)

    def paste_text(self, text: str) -> None:
        """Fast paste large text block into active canvas input."""
        fast_paste(text)

    def press_key(self, key: str) -> None:
        """Press a keyboard key."""
        press_single_key(key)


class ParallelDesktopController:
    """High-level controller for the parallel isolated desktop canvas (Desktop 2).
    
    Operates strictly within the isolated canvas window without touching
    the host operating system cursor or interfering with user multitasking.
    """

    def __init__(self, base_url: str = "http://127.0.0.1:8765"):
        from canvas_client import CanvasClient
        self.client = CanvasClient(base_url=base_url)

    def is_running(self) -> bool:
        return self.client.is_alive()

    def status(self) -> Dict[str, Any]:
        return self.client.status()

    def navigate(self, url: str) -> Dict[str, Any]:
        return self.client.navigate(url)

    def move(self, x: int, y: int, duration: float = 0.3) -> Dict[str, Any]:
        return self.client.move(x, y, duration=duration)

    def click(self, x: int, y: int, button: str = "left") -> Dict[str, Any]:
        return self.client.click(x, y, button=button)

    def type_text(self, text: str, delay: float = 0.04) -> Dict[str, Any]:
        return self.client.type_text(text, delay=delay)

    def press(self, key: str) -> Dict[str, Any]:
        return self.client.press(key)

    def scroll(self, delta_y: int) -> Dict[str, Any]:
        return self.client.scroll(delta_y)

    def capture(self) -> Dict[str, Any]:
        return self.client.capture()

    def transcribe(self, detailed: bool = False) -> Dict[str, Any]:
        return self.client.ocr(detailed=detailed)

    def order_chocolate(self, item: str = "KitKat") -> Dict[str, Any]:
        return self.client.order_chocolate(item=item)

