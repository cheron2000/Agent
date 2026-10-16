"""
eyes_mcp.py  -  Model Context Protocol (MCP) Server for EYES
Exposes the EYES Vision Engine to any MCP-compliant AI client (Claude Desktop, Cursor, Continue, Antigravity, etc.)
"""

import sys
import json
import asyncio
from typing import Optional, List, Dict, Any

from mcp.server.mcpserver import MCPServer
import eyes
from prompt_enhancer import PromptEnhancer, MASTER_AI_EYES_SYSTEM_PROMPT

# ── Initialize MCPServer ─────────────────────────────────────────────────────
server = MCPServer("eyes")


# ── MCP Tools ────────────────────────────────────────────────────────────────

@server.tool()
def screen_capture(save: bool = True, include_base64: bool = False) -> str:
    """
    Capture the current desktop screen.
    Returns the file path, dimensions, and optional base64 representation.
    """
    res = eyes.capture(save=save, include_base64=include_base64)
    return json.dumps(res, indent=2)


@server.tool()
def screen_ocr(detailed: bool = False) -> str:
    """
    Extract visible text from the desktop screen using OCR.
    If detailed is True, returns word bounding boxes and spatial coordinates.
    """
    res = eyes.read_text(detailed=detailed)
    return json.dumps(res, indent=2)


@server.tool()
def screen_map(columns: int = 12, rows: int = 8, min_confidence: int = 25) -> str:
    """Create an Excel-style spatial transcription of the screen.
    Each OCR element includes a cell such as H4 plus its exact bounding box.
    """
    res = eyes.screen_map(columns=columns, rows=rows, min_confidence=min_confidence)
    return json.dumps(res, indent=2)


@server.tool()
def screen_find(target: str, min_confidence: int = 30) -> str:
    """
    Search the screen for a specific text string or UI label.
    Returns the exact center (x, y) coordinates and bounding box if found.
    """
    res = eyes.find_on_screen(target=target, min_confidence=min_confidence)
    return json.dumps(res, indent=2)


@server.tool()
def screen_describe(prompt: str = "") -> str:
    """
    Obtain a rich semantic description of what is displayed on the screen using a vision model.
    Pass a custom prompt to ask specific questions about the screen layout.
    """
    res = eyes.describe(prompt=prompt if prompt else None)
    return json.dumps(res, indent=2)


@server.tool()
def screen_click(
    x: Optional[int] = None,
    y: Optional[int] = None,
    target: Optional[str] = None,
    click_type: str = "left"
) -> str:
    """
    Click at specific (x, y) coordinates or automatically locate and click a target text label.
    click_type can be 'left', 'right', or 'double'.
    """
    res = eyes.click(x=x, y=y, target=target, click_type=click_type)
    return json.dumps(res, indent=2)


@server.tool()
def screen_type(text: str, press_enter: bool = False) -> str:
    """
    Type text into the currently active / focused window or input field.
    Set press_enter=True to submit immediately after typing.
    """
    res = eyes.type_text(text=text, press_enter=press_enter)
    return json.dumps(res, indent=2)


@server.tool()
def screen_press_key(key: str) -> str:
    """
    Press a keyboard key or hotkey shortcut (e.g. 'enter', 'tab', 'escape', 'ctrl+c', 'alt+tab').
    """
    if "+" in key:
        keys = [k.strip().lower() for k in key.split("+")]
        res = eyes.press_key(keys)
    else:
        res = eyes.press_key(key.strip().lower())
    return json.dumps(res, indent=2)


@server.tool()
def screen_scroll(clicks: int = -3) -> str:
    """
    Scroll the mouse wheel. Negative values scroll down, positive values scroll up.
    """
    res = eyes.scroll(clicks=clicks)
    return json.dumps(res, indent=2)


@server.tool()
def screen_get_info() -> str:
    """
    Get screen resolution, active display bounds, and current mouse cursor position.
    """
    res = eyes.get_screen_info()
    return json.dumps(res, indent=2)


@server.tool()
def enhance_vision_prompt(
    task: str,
    target_application: Optional[str] = None,
    context_hints: Optional[str] = None
) -> str:
    """
    Transform a raw or vague desktop task into an enhanced, vision-grounded prompt.
    Produces an actionable strategy, target detection cues, and verification criteria.
    """
    hints = [h.strip() for h in context_hints.split(",")] if context_hints else None
    enhancer = PromptEnhancer()
    res = enhancer.enhance_task_prompt(
        raw_task=task,
        target_application=target_application,
        context_hints=hints
    )
    return json.dumps(res, indent=2)


# ── MCP Prompts ──────────────────────────────────────────────────────────────

@server.prompt()
def eyes_master_prompt() -> str:
    """The master cognitive system prompt for any vision-enabled AI agent."""
    return MASTER_AI_EYES_SYSTEM_PROMPT


if __name__ == "__main__":
    # Run standard MCP server over stdio
    server.run(transport="stdio")
