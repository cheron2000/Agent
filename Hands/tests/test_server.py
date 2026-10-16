"""Unit tests for AgentHands MCP server tools."""

import pytest
from unittest.mock import patch
from agent_hands.server import (
    hands_get_status,
    hands_list_windows,
    hands_press_key,
    hands_hotkey,
    hands_type_text,
    hands_paste_text,
    hands_click,
    hands_scroll,
)



def test_hands_get_status():
    """Verify hands_get_status returns valid metadata."""
    res = hands_get_status()
    assert res["status"] == "ready"
    assert "screen_resolution" in res
    assert "available_profiles" in res
    assert "natural" in res["available_profiles"]
    assert res["failsafe_enabled"] is True


def test_hands_list_windows():
    """Verify hands_list_windows executes without crash."""
    res = hands_list_windows()
    assert res["status"] == "success"
    assert isinstance(res["windows"], list)


@patch("agent_hands.server.press_single_key")
def test_hands_press_key(mock_press):
    """Verify hands_press_key invokes key presses."""
    res = hands_press_key(key="enter", count=2)
    assert res["status"] == "success"
    assert mock_press.call_count == 2


@patch("agent_hands.server.execute_hotkey")
def test_hands_hotkey(mock_hotkey):
    """Verify hands_hotkey triggers the hotkey sequence."""
    res = hands_hotkey(keys="ctrl+c")
    assert res["status"] == "success"
    mock_hotkey.assert_called_once_with("ctrl+c")


@patch("agent_hands.server.TypingEngine.type_text")
def test_hands_type_text(mock_type):
    """Verify hands_type_text calls engine with parameters."""
    mock_type.return_value = {
        "chars_typed": 5,
        "typos_corrected": 0,
        "elapsed_seconds": 0.5,
        "actual_wpm": 60.0,
    }
    res = hands_type_text(text="Hello", wpm=70, profile="fast")
    assert res["status"] == "success"
    assert "stats" in res
    assert res["stats"]["chars_typed"] == 5


@patch("agent_hands.server.click")
def test_hands_click(mock_click):
    """Verify hands_click invokes click action."""
    mock_click.return_value = {"status": "success", "x": 100, "y": 200, "clicks": 1, "button": "left"}
    res = hands_click(x=100, y=200, button="left")
    assert res["status"] == "success"
    mock_click.assert_called_once_with(x=100, y=200, button="left", clicks=1, interval=0.1, window_title=None)


@patch("agent_hands.server.scroll")
def test_hands_scroll(mock_scroll):
    """Verify hands_scroll invokes scroll action."""
    mock_scroll.return_value = {"status": "success", "clicks": -5, "direction": "down"}
    res = hands_scroll(clicks=-5, smooth=True)
    assert res["status"] == "success"
    mock_scroll.assert_called_once_with(clicks=-5, x=None, y=None, smooth=True, horizontal=False, window_title=None)


@patch("agent_hands.server.fast_paste")
def test_hands_paste_text(mock_paste):
    """Verify hands_paste_text invokes fast_paste."""
    res = hands_paste_text(text="hello world")
    assert res["status"] == "success"
    mock_paste.assert_called_once_with("hello world")


