"""Direct controller for an agent operating the real Windows desktop.

This module deliberately has no virtual canvas or browser sandbox.  It uses
Eyes for desktop perception and AgentHands for mouse/keyboard actions on the
currently visible Windows desktop.
"""

import logging
import os
import sys
from contextlib import contextmanager
from typing import Any, Dict, Optional, Tuple

ROOT = os.path.dirname(__file__)
sys.path.extend([os.path.join(ROOT, "Eyes"), os.path.join(ROOT, "Hands")])

# ---------------------------------------------------------------------------
# Module-level logger
# ---------------------------------------------------------------------------

_log_formatter = logging.Formatter("%(asctime)s %(levelname)s [ai_controller] %(message)s")

_file_handler = logging.FileHandler(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "err.log"),
    encoding="utf-8",
)
_file_handler.setFormatter(_log_formatter)

_console_handler = logging.StreamHandler()
_console_handler.setFormatter(_log_formatter)

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
logger.addHandler(_file_handler)
logger.addHandler(_console_handler)

import eyes
from agent_hands.engine import TypingEngine
from agent_hands.keyboard import fast_paste, press_single_key
from agent_hands.mouse import click, move_to, scroll
from agent_hands.windows import focus_window, get_active_window_title, list_windows


class DesktopAgentController:
    """Perceive and operate the user's actual desktop through Eyes and AgentHands."""

    @contextmanager
    def task(self, task_name: str = "desktop_task"):
        """Track screenshots generated during a task and clean them on exit."""
        session = eyes.start_task(task_name)
        try:
            yield self
        finally:
            eyes.end_task()

    # Perception
    def screen_info(self) -> Dict[str, Any]:
        return eyes.get_screen_info()

    def capture(self, save: bool = True) -> Dict[str, Any]:
        return eyes.capture(save=save)

    def transcribe(self, detailed: bool = False) -> Dict[str, Any]:
        return eyes.read_text(detailed=detailed)

    def find(self, target: str, min_confidence: int = 30) -> Dict[str, Any]:
        return eyes.find_on_screen(target, min_confidence=min_confidence)

    def describe(self, prompt: Optional[str] = None) -> Dict[str, Any]:
        return eyes.describe(prompt=prompt)

    def windows(self) -> Dict[str, Any]:
        return {
            "active_window": get_active_window_title(),
            "windows": list_windows(),
        }

    # Real desktop input
    def focus(self, window_title: str) -> bool:
        return focus_window(window_title)

    def move(self, x: int, y: int, duration: float = 0.2) -> Dict[str, Any]:
        return move_to(x=x, y=y, duration=duration)

    def click(
        self,
        x: Optional[int] = None,
        y: Optional[int] = None,
        button: str = "left",
        clicks: int = 1,
    ) -> Dict[str, Any]:
        return click(x=x, y=y, button=button, clicks=clicks)

    def scroll(self, clicks: int, x: Optional[int] = None, y: Optional[int] = None) -> Dict[str, Any]:
        return scroll(clicks=clicks, x=x, y=y, smooth=True)

    def type_text(self, text: str, profile: str = "natural", typos: bool = False) -> Dict[str, Any]:
        """Send simulated keyboard input to the active Windows application."""
        return TypingEngine(profile=profile).type_text(text=text, introduce_typos=typos)

    def paste_text(self, text: str) -> None:
        fast_paste(text)

    def press_key(self, key: str) -> None:
        press_single_key(key)


class CanvasAIController:
    """Orchestration bridge for the PyQt6 native canvas.

    Reads canvas_state.json via get_canvas_bounds(), pushes those bounds into
    both eyes.set_canvas_region() and hands_mouse.set_canvas_bounds(), and
    exposes a context-manager (task(name)) that wraps a TaskSession.  On exit
    the session auto-deletes every screenshot taken during that task.
    """

    def __init__(self):
        # Import here so that the module is importable even without canvas running
        from canvas_desktop import get_canvas_bounds as _gcb
        self._get_canvas_bounds = _gcb

        import eyes as _eyes_module
        self._eyes = _eyes_module

        from agent_hands import mouse as _hands_mouse
        self._hands_mouse = _hands_mouse

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def sync_canvas_bounds(self) -> Optional[Tuple]:
        """Read canvas_state.json and push bounds into Eyes and AgentHands.

        Returns the bounds tuple on success, None if the canvas is unavailable.
        """
        try:
            bounds = self._get_canvas_bounds()
        except RuntimeError as e:
            logger.error("Canvas bounds unavailable: %s", e)
            return None

        if bounds:
            x, y, w, h = bounds
            self._eyes.set_canvas_region(x, y, w, h)
            self._hands_mouse.set_canvas_bounds(x, y, w, h)
        return bounds

    # ------------------------------------------------------------------
    # Task lifecycle
    # ------------------------------------------------------------------

    @contextmanager
    def task(self, task_name: str = "canvas_task"):
        """Track screenshots generated during a task and clean them on exit."""
        self.sync_canvas_bounds()
        session = self._eyes.start_task(task_name)
        logger.info("[TASK START] Started Task: %s (Ephemeral Storage Active)", task_name)
        try:
            yield self
        finally:
            deleted = self._eyes.end_task()
            logger.info(
                "[CLEANUP] Task %s completed. Purged %d ephemeral screenshot(s).",
                task_name,
                deleted,
            )

    # ------------------------------------------------------------------
    # Perception
    # ------------------------------------------------------------------

    def capture(self, save: bool = True) -> Dict[str, Any]:
        return self._eyes.capture(save=save)

    def transcribe(self, detailed: bool = False) -> Dict[str, Any]:
        return self._eyes.read_text(detailed=detailed)

    def find_on_canvas(self, target: str, min_confidence: int = 30) -> Dict[str, Any]:
        return self._eyes.find_on_screen(target, min_confidence=min_confidence)

    def describe(self, prompt: Optional[str] = None) -> Dict[str, Any]:
        return self._eyes.describe(prompt=prompt)

    # ------------------------------------------------------------------
    # Input
    # ------------------------------------------------------------------

    def focus(self, window_title: str) -> bool:
        return focus_window(window_title)

    def move(self, x: int, y: int, duration: float = 0.2) -> Dict[str, Any]:
        return move_to(x=x, y=y, duration=duration)

    def click(
        self,
        x: Optional[int] = None,
        y: Optional[int] = None,
        button: str = "left",
        clicks: int = 1,
    ) -> Dict[str, Any]:
        return click(x=x, y=y, button=button, clicks=clicks)

    def double_click(self, x: Optional[int] = None, y: Optional[int] = None) -> Dict[str, Any]:
        return click(x=x, y=y, button="left", clicks=2)

    def scroll(self, clicks: int, x: Optional[int] = None, y: Optional[int] = None) -> Dict[str, Any]:
        return scroll(clicks=clicks, x=x, y=y, smooth=True)

    def type_text(self, text: str, profile: str = "natural", typos: bool = False) -> Dict[str, Any]:
        """Send simulated keyboard input to the active application."""
        return TypingEngine(profile=profile).type_text(text=text, introduce_typos=typos)

    def paste_text(self, text: str) -> None:
        fast_paste(text)

    def press_key(self, key: str) -> None:
        press_single_key(key)


if __name__ == "__main__":
    controller = DesktopAgentController()
    logger.info("%s", controller.screen_info())
