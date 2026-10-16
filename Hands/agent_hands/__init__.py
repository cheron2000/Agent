"""AgentHands: Keyboard Hands for Any AI Agent with Human-Like Typing Simulation."""

from .config import PROFILES, TypingProfile
from .engine import TypingEngine
from .keyboard import execute_hotkey, fast_paste, press_single_key, key_down, key_up
from .mouse import (
    click,
    double_click,
    right_click,
    scroll,
    move_to,
    drag_to,
    get_mouse_position,
    set_canvas_bounds,
    get_canvas_bounds,
)
from .windows import find_window, focus_window, get_active_window_title, list_windows
from .typos import get_adjacent_typo

__version__ = "0.2.0"

__all__ = [
    "TypingEngine",
    "TypingProfile",
    "PROFILES",
    "press_single_key",
    "key_down",
    "key_up",
    "execute_hotkey",
    "fast_paste",
    "click",
    "double_click",
    "right_click",
    "scroll",
    "move_to",
    "drag_to",
    "get_mouse_position",
    "set_canvas_bounds",
    "get_canvas_bounds",
    "list_windows",
    "find_window",
    "focus_window",
    "get_active_window_title",
    "get_adjacent_typo",
]

