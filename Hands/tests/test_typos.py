"""Unit tests for typo generation and QWERTY adjacency model."""

import pytest
from agent_hands.typos import QWERTY_ADJACENT, get_adjacent_typo


def test_qwerty_adjacency_keys():
    """Verify standard keys exist in adjacency map."""
    assert "a" in QWERTY_ADJACENT
    assert "e" in QWERTY_ADJACENT
    assert "w" in QWERTY_ADJACENT
    assert "s" in QWERTY_ADJACENT
    assert len(QWERTY_ADJACENT["a"]) > 0


def test_adjacent_typo_case_preservation():
    """Verify that casing is preserved when generating typos."""
    lower_typo = get_adjacent_typo("a")
    assert lower_typo is not None
    assert lower_typo.islower()
    assert lower_typo in QWERTY_ADJACENT["a"]

    upper_typo = get_adjacent_typo("A")
    assert upper_typo is not None
    assert upper_typo.isupper()
    assert upper_typo.lower() in QWERTY_ADJACENT["a"]


def test_adjacent_typo_unmapped_char():
    """Verify non-standard or special characters return None gracefully."""
    assert get_adjacent_typo("") is None
    assert get_adjacent_typo(" ") is None
    assert get_adjacent_typo("😊") is None
