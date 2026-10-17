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
from agent_hands.keyboard import fast_paste, press_single_key, execute_hotkey
from agent_hands.mouse import click, move_to, scroll
from agent_hands.windows import focus_window, get_active_window_title, list_windows

try:
    from Context import ContextAnalyzer, ContextReport
except ImportError:
    try:
        from .Context import ContextAnalyzer, ContextReport
    except ImportError:
        ContextAnalyzer = None
        ContextReport = None


class DesktopAgentController:
    """Perceive and operate the user's actual desktop through Eyes, Context, and AgentHands."""

    def __init__(self):
        self.context = ContextAnalyzer() if ContextAnalyzer else None

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

    def observe(
        self,
        save_annotated: bool = True,
        max_elements: int = 100,
        annotate: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """Capture unified observation with numbered UI elements for LLM grounding."""
        if annotate is not None:
            save_annotated = annotate
        return eyes.observe(save_annotated=save_annotated, max_elements=max_elements)

    def zoom(
        self,
        region: Optional[List[int]] = None,
        element_id: Optional[int] = None,
        scale: float = 3.0,
    ) -> Dict[str, Any]:
        """Crop and zoom into a bounding box or element ID with high-resolution OCR."""
        return eyes.zoom(region=region, element_id=element_id, scale=scale)

    def wait_for_text(self, target: str, timeout_s: float = 5.0) -> Dict[str, Any]:
        """Wait until target text appears on screen."""
        return eyes.wait_for_text(target=target, timeout_s=timeout_s)

    def click_element(
        self,
        element_id: int,
        button: str = "left",
        clicks: int = 1,
    ) -> Dict[str, Any]:
        """Click an element by its observation ID without computing pixel coordinates."""
        coords = eyes.resolve_element_center(element_id)
        if not coords:
            return {"success": False, "error": f"Element ID {element_id} not found in active observation"}
        cx, cy = coords
        return click(x=cx, y=cy, button=button, clicks=clicks)

    def resolve_element_center(self, element_id: int) -> Optional[Tuple[int, int]]:
        """Resolve element ID to physical screen center coordinates (cx, cy)."""
        return eyes.resolve_element_center(element_id)

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
    def paste_text(self, text: str, restore_clipboard: bool = False) -> None:
        """Paste bulk text through the clipboard instead of simulating each key.

        Prefer this for long emails, prompts, and reports. Use type_text() when
        realistic per-key input is specifically needed by the target application.
        """
        fast_paste(text, restore_clipboard=restore_clipboard)

    def press_key(self, key: str) -> None:
        press_single_key(key)

    def hotkey(self, *keys: str) -> None:
        """Execute a key combination with natural human staggering (e.g. 'ctrl', 't')."""
        execute_hotkey(list(keys))

    # ── Context Layer Integration ────────────────────────────────────────────
    def analyze_context(self, observation: Optional[Any] = None, goal: Optional[str] = None) -> Any:
        """Analyze current screen context, formulate situational rationale, and suggest next action."""
        if self.context is None:
            raise RuntimeError("Context engine is not available.")
        obs = observation if observation is not None else self.observe(annotate=True)
        return self.context.analyze(obs, goal=goal)

    def step_with_context(self, goal: Optional[str] = None, execute: bool = True) -> Dict[str, Any]:
        """Perform one autonomous OODA loop step: Observe -> Contextualize -> Act.
        
        Analyzes the current screen, logs the human-readable utterance (reasoning),
        and executes the recommended action if execute=True.
        """
        obs = self.observe(annotate=True)
        report = self.analyze_context(observation=obs, goal=goal)
        logger.info("[Context] %s", report.utterance)

        action_result = None
        if execute and report.recommendation:
            rec = report.recommendation
            act_type = rec.action_type
            if act_type == "click_element" and rec.target_id is not None:
                action_result = self.click_element(rec.target_id)
            elif act_type == "hotkey" and rec.hotkey:
                self.hotkey(*rec.hotkey)
                action_result = {"status": "success", "action": "hotkey", "keys": rec.hotkey}
            elif act_type == "type_text" and rec.text:
                action_result = self.type_text(rec.text)
            elif act_type == "wait":
                time.sleep(rec.params.get("seconds", 2.0))
                action_result = {"status": "success", "action": "wait"}

        return {
            "success": True,
            "report": report.to_dict(),
            "utterance": report.utterance,
            "action_result": action_result,
            "executed": execute,
        }


if __name__ == "__main__":
    controller = DesktopAgentController()
    logger.info("%s", controller.screen_info())


