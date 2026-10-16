"""AgentHands Model Context Protocol (MCP) Server.
Gives any AI Agent physical keyboard hands with human-like typing simulation.
"""

import os
import sys
from typing import Any, Dict, List, Optional
import pyautogui

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Ensure parent directory is in sys.path when executed directly as a script
if __package__ is None or not __package__:
    parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if parent_dir not in sys.path:
        sys.path.insert(0, parent_dir)
    __package__ = "agent_hands"

from mcp.server.mcpserver import MCPServer
from .config import PROFILES
from .engine import TypingEngine
from .keyboard import execute_hotkey, fast_paste, press_single_key
from .mouse import click, double_click, right_click, scroll, move_to, drag_to, get_mouse_position
from .windows import focus_window, get_active_window_title, list_windows


# Create the MCP Server
mcp = MCPServer("AgentHands")


@mcp.tool(
    name="hands_type_text",
    description=(
        "Type text using the keyboard with human-like cadence, realistic speed variation, "
        "natural punctuation micro-pauses, and optional human typo self-corrections."
    ),
)
def hands_type_text(
    text: str,
    wpm: Optional[float] = None,
    human_like: bool = True,
    introduce_typos: bool = False,
    typo_rate: Optional[float] = 0.015,
    profile: str = "natural",
    window_title: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Type text on the keyboard.

    Args:
        text: The string to type.
        wpm: Speed in Words Per Minute (e.g., 65 for normal, 100 for fast). If omitted, uses profile default.
        human_like: If True, simulates human speed variation and natural pauses.
        introduce_typos: If True, simulates occasional adjacent-key typos and backspace corrections.
        typo_rate: Typo frequency per character (default 0.015 = 1.5%).
        profile: Typing profile name: 'natural', 'fast', 'careful', or 'coder'.
        window_title: Optional window title or pattern to focus before typing.
    """
    engine = TypingEngine(profile=profile)
    stats = engine.type_text(
        text=text,
        wpm=wpm,
        human_like=human_like,
        introduce_typos=introduce_typos,
        typo_rate=typo_rate,
        window_title=window_title,
    )
    return {
        "status": "success",
        "message": f"Successfully typed {stats['chars_typed']} characters at ~{stats['actual_wpm']} WPM.",
        "stats": stats,
    }


@mcp.tool(
    name="hands_press_key",
    description="Press a specific keyboard key (e.g. enter, tab, esc, backspace, space, up, down, f5).",
)
def hands_press_key(
    key: str,
    count: int = 1,
    dwell_time: float = 0.05,
    window_title: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Press and release a keyboard key.

    Args:
        key: Key name (e.g., 'enter', 'tab', 'esc', 'backspace', 'space', 'down', 'f5').
        count: Number of times to press the key (default: 1).
        dwell_time: Dwell duration in seconds per press (default: 0.05s).
        window_title: Optional window title to focus before pressing.
    """
    if window_title:
        focus_window(window_title)

    count = max(1, min(count, 50))
    for _ in range(count):
        press_single_key(key, dwell_time=dwell_time)

    return {
        "status": "success",
        "message": f"Pressed key '{key}' {count} time(s).",
    }


@mcp.tool(
    name="hands_hotkey",
    description="Trigger a key combination shortcut (e.g., ['ctrl', 'c'], ['alt', 'tab'], ['ctrl', 'shift', 'p'], or 'win+r').",
)
def hands_hotkey(
    keys: str,
    window_title: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Trigger a keyboard shortcut / hotkey.

    Args:
        keys: Key combination as a string, e.g. 'ctrl+c', 'ctrl+shift+p', 'alt+tab', 'win+r'.
        window_title: Optional window title to focus before triggering the hotkey.
    """
    if window_title:
        focus_window(window_title)

    execute_hotkey(keys)
    return {
        "status": "success",
        "message": f"Executed hotkey '{keys}'.",
    }


@mcp.tool(
    name="hands_paste_text",
    description="Instantly paste a large block of text or code into the active window using system clipboard (Ctrl+V).",
)
def hands_paste_text(
    text: str,
    window_title: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Paste text immediately via clipboard.

    Args:
        text: The text or codeblock to paste.
        window_title: Optional window title to focus before pasting.
    """
    if window_title:
        focus_window(window_title)

    fast_paste(text)
    return {
        "status": "success",
        "message": f"Pasted {len(text)} characters into active window.",
    }


@mcp.tool(
    name="hands_list_windows",
    description="List all currently open and visible application windows on the desktop so the agent can inspect and focus them.",
)
def hands_list_windows() -> Dict[str, Any]:
    """List open desktop windows."""
    windows = list_windows()
    return {
        "status": "success",
        "count": len(windows),
        "windows": windows,
    }


@mcp.tool(
    name="hands_focus_window",
    description="Bring a target application window to the foreground and grant it keyboard focus.",
)
def hands_focus_window(window_title: str) -> Dict[str, Any]:
    """
    Focus and activate a window.

    Args:
        window_title: Partial title or name of the target window (e.g., 'Notepad', 'Chrome').
    """
    success = focus_window(window_title)
    active = get_active_window_title()
    return {
        "status": "success" if success else "not_found",
        "focused": success,
        "active_window": active,
    }


@mcp.tool(
    name="hands_click",
    description="Click anywhere on the screen or in a target window with left, right, middle, or double click.",
)
def hands_click(
    x: Optional[int] = None,
    y: Optional[int] = None,
    button: str = "left",
    clicks: int = 1,
    interval: float = 0.1,
    window_title: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Click mouse button at specific (x, y) coordinates or active location.

    Args:
        x: Target X pixel coordinate (optional).
        y: Target Y pixel coordinate (optional).
        button: 'left', 'right', or 'middle' (default 'left').
        clicks: 1 for single click, 2 for double click.
        interval: Delay between multiple clicks in seconds.
        window_title: Optional window title to focus before clicking.
    """
    return click(
        x=x,
        y=y,
        button=button,
        clicks=clicks,
        interval=interval,
        window_title=window_title,
    )


@mcp.tool(
    name="hands_scroll",
    description="Scroll the mouse wheel up or down (smooth or instant), vertically or horizontally.",
)
def hands_scroll(
    clicks: int,
    x: Optional[int] = None,
    y: Optional[int] = None,
    smooth: bool = True,
    horizontal: bool = False,
    window_title: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Scroll mouse wheel.

    Args:
        clicks: Scroll amount. Positive for UP, negative for DOWN.
        x: Optional X coordinate to position cursor over before scrolling.
        y: Optional Y coordinate to position cursor over before scrolling.
        smooth: If True, simulates natural human finger wheel rotation.
        horizontal: If True, scrolls horizontally (left for negative, right for positive).
        window_title: Optional window title to focus before scrolling.
    """
    return scroll(
        clicks=clicks,
        x=x,
        y=y,
        smooth=smooth,
        horizontal=horizontal,
        window_title=window_title,
    )


@mcp.tool(
    name="hands_move_mouse",
    description="Move mouse cursor to specific (x, y) coordinates on the screen.",
)
def hands_move_mouse(
    x: int,
    y: int,
    duration: float = 0.2,
    window_title: Optional[str] = None,
) -> Dict[str, Any]:
    """Move mouse cursor smoothly."""
    return move_to(x=x, y=y, duration=duration, window_title=window_title)


@mcp.tool(
    name="hands_get_status",
    description="Get current status of keyboard hands, screen size, active window, and typing profiles.",
)
def hands_get_status() -> Dict[str, Any]:
    """Get system and keyboard status."""
    screen_w, screen_h = pyautogui.size()
    active_win = get_active_window_title()
    return {
        "status": "ready",
        "screen_resolution": f"{screen_w}x{screen_h}",
        "active_window": active_win,
        "available_profiles": list(PROFILES.keys()),
        "failsafe_enabled": pyautogui.FAILSAFE,
    }


def main():
    """Run the MCP server over stdio transport."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
