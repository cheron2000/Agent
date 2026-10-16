"""Configuration and typing profiles for AgentHands."""

from dataclasses import dataclass
from typing import Dict, Any


@dataclass
class TypingProfile:
    name: str
    target_wpm: float
    wpm_variance: float          # Standard deviation ratio (e.g. 0.25 = ±25% variation)
    keystroke_dwell_ms: float    # How long a key is held down (ms)
    space_pause_mult: float      # Multiplier for inter-word pause
    sentence_pause_ms: float     # Pause after . ! ?
    clause_pause_ms: float       # Pause after , ; :
    symbol_pause_mult: float     # Multiplier for tricky symbols / numbers
    typo_probability: float      # Chance of typo per character (0.0 to 1.0)
    typo_realize_delay_ms: float # Delay before realizing a mistake was made
    typo_correct_delay_ms: float # Delay before pressing backspace and continuing


# Predefined Profiles
PROFILES: Dict[str, TypingProfile] = {
    "natural": TypingProfile(
        name="natural",
        target_wpm=65.0,
        wpm_variance=0.25,
        keystroke_dwell_ms=45.0,
        space_pause_mult=1.4,
        sentence_pause_ms=380.0,
        clause_pause_ms=180.0,
        symbol_pause_mult=1.6,
        typo_probability=0.015,
        typo_realize_delay_ms=220.0,
        typo_correct_delay_ms=120.0,
    ),
    "fast": TypingProfile(
        name="fast",
        target_wpm=105.0,
        wpm_variance=0.15,
        keystroke_dwell_ms=30.0,
        space_pause_mult=1.2,
        sentence_pause_ms=160.0,
        clause_pause_ms=90.0,
        symbol_pause_mult=1.2,
        typo_probability=0.005,
        typo_realize_delay_ms=120.0,
        typo_correct_delay_ms=80.0,
    ),
    "careful": TypingProfile(
        name="careful",
        target_wpm=38.0,
        wpm_variance=0.30,
        keystroke_dwell_ms=65.0,
        space_pause_mult=1.7,
        sentence_pause_ms=550.0,
        clause_pause_ms=300.0,
        symbol_pause_mult=2.0,
        typo_probability=0.025,
        typo_realize_delay_ms=300.0,
        typo_correct_delay_ms=180.0,
    ),
    "coder": TypingProfile(
        name="coder",
        target_wpm=72.0,
        wpm_variance=0.20,
        keystroke_dwell_ms=40.0,
        space_pause_mult=1.3,
        sentence_pause_ms=280.0,
        clause_pause_ms=140.0,
        symbol_pause_mult=1.3,
        typo_probability=0.008,
        typo_realize_delay_ms=180.0,
        typo_correct_delay_ms=100.0,
    ),
}
