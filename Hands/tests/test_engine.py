"""Unit tests for TypingEngine mechanics and timing profiles."""

import pytest
from unittest.mock import patch, MagicMock
from agent_hands.config import PROFILES, TypingProfile
from agent_hands.engine import TypingEngine


def test_engine_init_with_profile_name():
    """Verify initialization with profile name string."""
    engine = TypingEngine("fast")
    assert engine.profile.name == "fast"
    assert engine.profile.target_wpm == 105.0


def test_engine_init_with_custom_profile():
    """Verify initialization with custom TypingProfile object."""
    custom = TypingProfile(
        name="custom",
        target_wpm=50.0,
        wpm_variance=0.2,
        keystroke_dwell_ms=40.0,
        space_pause_mult=1.5,
        sentence_pause_ms=300.0,
        clause_pause_ms=150.0,
        symbol_pause_mult=1.5,
        typo_probability=0.01,
        typo_realize_delay_ms=200.0,
        typo_correct_delay_ms=100.0,
    )
    engine = TypingEngine(custom)
    assert engine.profile.name == "custom"
    assert engine.profile.target_wpm == 50.0


def test_calc_char_delay_bounds():
    """Verify calculated character delay stays within reasonable physical bounds."""
    engine = TypingEngine("natural")
    base_delay = 0.15
    for _ in range(50):
        delay = engine._calc_char_delay(base_delay)
        assert delay >= 0.015
        assert delay <= base_delay * 2.8


@patch("pyautogui.write")
@patch("time.sleep")
def test_type_text_mocked_execution(mock_sleep, mock_write):
    """Verify typing flow without sending real physical keystrokes."""
    engine = TypingEngine("fast")
    text = "Hello, world!"
    stats = engine.type_text(text, human_like=True, introduce_typos=False)

    assert stats["chars_typed"] == len(text)
    assert stats["typos_corrected"] == 0
    assert mock_write.call_count > 0
