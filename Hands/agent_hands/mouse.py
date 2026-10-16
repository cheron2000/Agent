"""Mouse actions for AgentHands: click, double-click, right-click, drag, and smooth scrolling."""

import time
from typing import Any, Dict, Optional, Tuple, Union
import pyautogui

from .windows import focus_window

# Ensure fail-safe doesn't crash if cursor is temporarily positioned near screen edges
# PyAutoGUI fail-safe: moving cursor to exact corners (0,0) aborts if enabled
pyautogui.FAILSAFE = True

# ── Canvas Bounding ─────────────────────────────────────────────────────────
_ACTIVE_CANVAS_BOUNDS: Optional[Tuple[int, int, int, int]] = None


def set_canvas_bounds(bounds: Optional[Tuple[int, int, int, int]]):
    """Set active canvas (x, y, width, height) to restrict and clamp all mouse actions inside it."""
    global _ACTIVE_CANVAS_BOUNDS
    _ACTIVE_CANVAS_BOUNDS = bounds


def get_canvas_bounds() -> Optional[Tuple[int, int, int, int]]:
    """Get currently active canvas bounds."""
    return _ACTIVE_CANVAS_BOUNDS


def _clamp_to_bounds(x: int, y: int) -> Tuple[int, int]:
    """Clamp (x, y) coordinates to active canvas or primary display."""
    if _ACTIVE_CANVAS_BOUNDS:
        bx, by, bw, bh = _ACTIVE_CANVAS_BOUNDS
        # If relative coordinates were supplied (0..width, 0..height), translate to global
        if 0 <= x <= bw and 0 <= y <= bh and x < bx:
            target_x = bx + x
            target_y = by + y
        else:
            target_x = max(bx, min(int(x), bx + bw - 1))
            target_y = max(by, min(int(y), by + bh - 1))
        return target_x, target_y

    screen_w, screen_h = pyautogui.size()
    return max(0, min(int(x), screen_w - 1)), max(0, min(int(y), screen_h - 1))


def get_mouse_position() -> Tuple[int, int]:
    """Get the current cursor (x, y) coordinates on screen."""
    pos = pyautogui.position()
    return (int(pos.x), int(pos.y))


def move_to(
    x: int,
    y: int,
    duration: float = 0.2,
    window_title: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Move the mouse cursor smoothly to (x, y) coordinates.

    Args:
        x: Target X pixel coordinate.
        y: Target Y pixel coordinate.
        duration: Travel time in seconds for natural human movement (default 0.2s).
        window_title: Optional window title to bring to foreground first.

    Returns:
        Dictionary with status, coordinates, and error details if any.
    """
    if window_title:
        focus_window(window_title)
        time.sleep(0.2)

    target_x, target_y = _clamp_to_bounds(x, y)

    pyautogui.moveTo(target_x, target_y, duration=max(0.0, duration))
    return {
        "status": "success",
        "action": "move",
        "x": target_x,
        "y": target_y,
    }



def click(
    x: Optional[int] = None,
    y: Optional[int] = None,
    button: str = "left",
    clicks: int = 1,
    interval: float = 0.1,
    duration: float = 0.15,
    window_title: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Click at specific (x, y) coordinates or current mouse position.

    Args:
        x: Optional target X coordinate. If None, clicks at current cursor position.
        y: Optional target Y coordinate. If None, clicks at current cursor position.
        button: Mouse button ('left', 'right', 'middle'). Default 'left'.
        clicks: Number of clicks (1 for single, 2 for double). Default 1.
        interval: Time between multiple clicks in seconds.
        duration: Cursor movement travel duration before click.
        window_title: Optional window title to focus before clicking.

    Returns:
        Dictionary with click details and outcome.
    """
    if window_title:
        focus_window(window_title)
        time.sleep(0.2)

    button_clean = button.strip().lower()
    if button_clean not in ("left", "right", "middle", "primary", "secondary"):
        button_clean = "left"
    if button_clean == "primary":
        button_clean = "left"
    elif button_clean == "secondary":
        button_clean = "right"

    if x is not None and y is not None:
        target_x, target_y = _clamp_to_bounds(x, y)
        pyautogui.moveTo(target_x, target_y, duration=max(0.0, duration))
    else:
        target_x, target_y = get_mouse_position()
        if _ACTIVE_CANVAS_BOUNDS:
            target_x, target_y = _clamp_to_bounds(target_x, target_y)

    # Visual click feedback ripple
    try:
        from .visual_overlay import show_click_ripple
        show_click_ripple(target_x, target_y, button_clean)
    except Exception:
        pass

    # Perform click
    pyautogui.click(
        x=target_x,
        y=target_y,
        clicks=max(1, clicks),
        interval=max(0.0, interval),
        button=button_clean,
    )

    return {
        "status": "success",
        "action": f"{button_clean}_click" if clicks == 1 else f"{button_clean}_click_x{clicks}",
        "x": target_x,
        "y": target_y,
        "clicks": clicks,
        "button": button_clean,
    }


def double_click(
    x: Optional[int] = None,
    y: Optional[int] = None,
    window_title: Optional[str] = None,
) -> Dict[str, Any]:
    """Convenience helper for double-clicking left mouse button."""
    return click(x=x, y=y, button="left", clicks=2, interval=0.1, window_title=window_title)


def right_click(
    x: Optional[int] = None,
    y: Optional[int] = None,
    window_title: Optional[str] = None,
) -> Dict[str, Any]:
    """Convenience helper for right-clicking."""
    return click(x=x, y=y, button="right", clicks=1, window_title=window_title)


def scroll(
    clicks: int,
    x: Optional[int] = None,
    y: Optional[int] = None,
    smooth: bool = True,
    horizontal: bool = False,
    window_title: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Scroll mouse wheel vertically or horizontally.

    Args:
        clicks: Scroll amount. Positive values scroll UP, negative scroll DOWN.
        x: Optional X coordinate to position cursor over before scrolling.
        y: Optional Y coordinate to position cursor over before scrolling.
        smooth: If True, simulates natural human finger wheel rotation in micro-steps.
        horizontal: If True, scrolls horizontally (left for negative, right for positive).
        window_title: Optional window title to focus before scrolling.

    Returns:
        Dictionary with scroll details.
    """
    if window_title:
        focus_window(window_title)
        time.sleep(0.2)

    if x is not None and y is not None:
        target_x, target_y = _clamp_to_bounds(x, y)
        pyautogui.moveTo(target_x, target_y, duration=0.1)
    else:
        target_x, target_y = get_mouse_position()
        if _ACTIVE_CANVAS_BOUNDS:
            target_x, target_y = _clamp_to_bounds(target_x, target_y)

    if clicks == 0:
        return {
            "status": "success",
            "action": "scroll",
            "clicks": 0,
            "x": target_x,
            "y": target_y,
            "direction": "none",
        }

    direction = "up" if clicks > 0 else "down"
    if horizontal:
        direction = "right" if clicks > 0 else "left"

    if horizontal:
        # Horizontal scrolling
        try:
            pyautogui.hscroll(clicks, x=target_x, y=target_y)
        except (AttributeError, NotImplementedError):
            # Fallback using Shift+Scroll
            pyautogui.keyDown("shift")
            pyautogui.scroll(clicks, x=target_x, y=target_y)
            pyautogui.keyUp("shift")
    else:
        # Vertical scrolling
        if smooth and abs(clicks) >= 3:
            # Human-like staggered micro-scrolls
            step = 1 if clicks > 0 else -1
            total_steps = abs(clicks)
            for _ in range(total_steps):
                pyautogui.scroll(step * 100, x=target_x, y=target_y)
                time.sleep(0.02)
        else:
            # PyAutoGUI wheel units (1 click is typically 100-120 units on Windows)
            wheel_units = clicks * 100 if abs(clicks) <= 20 else clicks
            pyautogui.scroll(wheel_units, x=target_x, y=target_y)

    return {
        "status": "success",
        "action": "scroll",
        "clicks": clicks,
        "x": target_x,
        "y": target_y,
        "direction": direction,
        "horizontal": horizontal,
        "smooth": smooth,
    }


def drag_to(
    x: int,
    y: int,
    duration: float = 0.5,
    button: str = "left",
    window_title: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Drag mouse cursor to (x, y) with specified mouse button held down.

    Args:
        x: Target X coordinate.
        y: Target Y coordinate.
        duration: Drag movement duration.
        button: Button to hold down ('left', 'right', 'middle').
        window_title: Optional window title to focus before dragging.
    """
    if window_title:
        focus_window(window_title)
        time.sleep(0.2)

    target_x, target_y = _clamp_to_bounds(x, y)

    button_clean = button.strip().lower() if button else "left"
    pyautogui.dragTo(target_x, target_y, duration=duration, button=button_clean)

    return {
        "status": "success",
        "action": f"drag_{button_clean}",
        "x": target_x,
        "y": target_y,
    }
