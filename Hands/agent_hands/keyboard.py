"""Low-level keyboard actions, key mapping, and hotkey sequences."""

import time
from typing import List, Optional, Union
import pyautogui
import pyperclip

from .windows import ensure_interactive_desktop

# PyAutoGUI fail-safe settings
pyautogui.FAILSAFE = True

# Common key alias normalizer
KEY_ALIASES = {
    "return": "enter",
    "control": "ctrl",
    "escape": "esc",
    "windows": "win",
    "super": "win",
    "command": "win",
    "option": "alt",
    "del": "delete",
    "bksp": "backspace",
    "up": "up",
    "down": "down",
    "left": "left",
    "right": "right",
    "pgup": "pageup",
    "pgdn": "pagedown",
}


def normalize_key_name(key: str) -> str:
    """Normalize user/agent provided key names to PyAutoGUI compatible names."""
    k = key.strip().lower()
    return KEY_ALIASES.get(k, k)


def press_single_key(key: str, dwell_time: float = 0.05) -> None:
    """Press and release a single key with realistic dwell duration."""
    ensure_interactive_desktop()
    k = normalize_key_name(key)
    pyautogui.keyDown(k)
    time.sleep(dwell_time)
    pyautogui.keyUp(k)


def key_down(key: str) -> None:
    """Hold down a key without releasing."""
    pyautogui.keyDown(normalize_key_name(key))


def key_up(key: str) -> None:
    """Release a held down key."""
    pyautogui.keyUp(normalize_key_name(key))


def execute_hotkey(keys: Union[List[str], str], step_delay: float = 0.04) -> None:
    """
    Execute a key combination with natural human staggering.
    Example: ['ctrl', 'shift', 'p'] or 'ctrl+c'
    Presses keys in order, holds them, then releases in reverse order.
    """
    ensure_interactive_desktop()
    if isinstance(keys, str):
        # Split by '+' or '-' or space
        raw_keys = [k.strip() for k in keys.replace("+", " ").replace("-", " ").split()]
    else:
        raw_keys = keys

    normalized = [normalize_key_name(k) for k in raw_keys if k]
    if not normalized:
        return

    # Press keys down in forward order with slight stagger
    for k in normalized:
        pyautogui.keyDown(k)
        time.sleep(step_delay)

    # Brief hold duration while all keys are down
    time.sleep(step_delay * 1.5)

    # Release keys in reverse order
    for k in reversed(normalized):
        pyautogui.keyUp(k)
        time.sleep(step_delay)


def fast_paste(text: str, restore_clipboard: bool = False) -> None:
    """Paste large text blocks directly via system clipboard using Ctrl+V.
    
    If restore_clipboard is True, the previous clipboard content is preserved
    and restored after the paste operation.
    """
    previous = None
    if restore_clipboard:
        try:
            previous = pyperclip.paste()
        except Exception:
            previous = None

    pyperclip.copy(text)
    time.sleep(0.05)
    execute_hotkey(["ctrl", "v"])

    if restore_clipboard and previous is not None:
        time.sleep(0.05)
        try:
            pyperclip.copy(previous)
        except Exception:
            pass
