"""Unit tests for mouse actions (click, scroll, move, drag)."""

from unittest.mock import MagicMock, patch
import pytest

from agent_hands.mouse import (
    click,
    double_click,
    drag_to,
    get_mouse_position,
    move_to,
    right_click,
    scroll,
)


@patch("pyautogui.moveTo")
@patch("pyautogui.size", return_value=(1920, 1080))
def test_move_to(mock_size, mock_move):
    """Test mouse cursor movement with bounds clamping."""
    res = move_to(500, 300, duration=0.1)
    assert res["status"] == "success"
    assert res["x"] == 500
    assert res["y"] == 300
    mock_move.assert_called_once_with(500, 300, duration=0.1)


@patch("pyautogui.moveTo")
@patch("pyautogui.size", return_value=(1920, 1080))
def test_move_to_clamped(mock_size, mock_move):
    """Test movement outside bounds is clamped."""
    res = move_to(2500, -100)
    assert res["status"] == "success"
    assert res["x"] == 1919
    assert res["y"] == 0


@patch("pyautogui.click")
@patch("pyautogui.moveTo")
@patch("pyautogui.size", return_value=(1920, 1080))
def test_click_at_coords(mock_size, mock_move, mock_click):
    """Test single click at coordinates."""
    res = click(x=400, y=600, button="left")
    assert res["status"] == "success"
    assert res["x"] == 400
    assert res["y"] == 600
    assert res["clicks"] == 1
    assert res["button"] == "left"
    mock_click.assert_called_once_with(x=400, y=600, clicks=1, interval=0.1, button="left")


@patch("pyautogui.click")
@patch("pyautogui.moveTo")
@patch("pyautogui.size", return_value=(1920, 1080))
def test_double_click(mock_size, mock_move, mock_click):
    """Test double click convenience function."""
    res = double_click(x=300, y=200)
    assert res["status"] == "success"
    assert res["clicks"] == 2
    mock_click.assert_called_once_with(x=300, y=200, clicks=2, interval=0.1, button="left")


@patch("pyautogui.click")
@patch("pyautogui.moveTo")
@patch("pyautogui.size", return_value=(1920, 1080))
def test_right_click(mock_size, mock_move, mock_click):
    """Test right click convenience function."""
    res = right_click(x=350, y=250)
    assert res["status"] == "success"
    assert res["button"] == "right"
    mock_click.assert_called_once_with(x=350, y=250, clicks=1, interval=0.1, button="right")


@patch("pyautogui.scroll")
@patch("pyautogui.position", return_value=MagicMock(x=500, y=500))
def test_scroll_down(mock_pos, mock_scroll):
    """Test scroll down (negative clicks)."""
    res = scroll(-5, smooth=False)
    assert res["status"] == "success"
    assert res["direction"] == "down"
    assert res["clicks"] == -5
    mock_scroll.assert_called_once()


@patch("pyautogui.scroll")
@patch("pyautogui.position", return_value=MagicMock(x=500, y=500))
def test_scroll_up(mock_pos, mock_scroll):
    """Test scroll up (positive clicks)."""
    res = scroll(5, smooth=False)
    assert res["status"] == "success"
    assert res["direction"] == "up"
    assert res["clicks"] == 5
    mock_scroll.assert_called_once()


@patch("pyautogui.dragTo")
@patch("pyautogui.size", return_value=(1920, 1080))
def test_drag_to(mock_size, mock_drag):
    """Test mouse drag action."""
    res = drag_to(400, 300, duration=0.2, button="left")
    assert res["status"] == "success"
    assert res["x"] == 400
    assert res["y"] == 300
    mock_drag.assert_called_once_with(400, 300, duration=0.2, button="left")


@patch("pyautogui.position", return_value=MagicMock(x=640, y=480))
def test_get_mouse_position(mock_pos):
    """Test get_mouse_position."""
    pos = get_mouse_position()
    assert pos == (640, 480)

