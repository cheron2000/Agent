"""Human-like typing simulation engine with natural cadence, pauses, and typo modeling."""

import random
import time
from typing import Callable, Dict, Optional, Union
import pyautogui

from .config import PROFILES, TypingProfile
from .keyboard import press_single_key
from .typos import get_adjacent_typo
from .windows import ensure_interactive_desktop, focus_window


class TypingEngine:
    """Simulates realistic human keyboard typing."""

    def __init__(self, profile: Union[str, TypingProfile] = "natural"):
        if isinstance(profile, str):
            self.profile = PROFILES.get(profile.lower(), PROFILES["natural"])
        else:
            self.profile = profile

    def _calc_char_delay(self, base_delay: float) -> float:
        """Calculate randomized keystroke delay using Gaussian distribution."""
        variance = self.profile.wpm_variance * base_delay
        delay = random.gauss(base_delay, variance)
        # Clamp between reasonable physical bounds
        min_bound = max(0.015, base_delay * 0.4)
        max_bound = base_delay * 2.8
        return max(min_bound, min(delay, max_bound))

    def _calc_dwell_time(self) -> float:
        """Calculate duration for holding key down."""
        dwell_sec = self.profile.keystroke_dwell_ms / 1000.0
        return max(0.015, random.gauss(dwell_sec, dwell_sec * 0.25))

    def type_text(
        self,
        text: str,
        wpm: Optional[float] = None,
        human_like: bool = True,
        introduce_typos: bool = False,
        typo_rate: Optional[float] = None,
        window_title: Optional[str] = None,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
    ) -> Dict[str, Union[int, float, str]]:
        """
        Type the specified text with human-like cadence and optional typo corrections.

        Args:
            text: The string to type.
            wpm: Target typing speed in Words Per Minute (overrides profile if provided).
            human_like: If True, applies variable jitter, micro-pauses, and natural cadence.
            introduce_typos: If True, simulates occasional adjacent-key typos and backspace corrections.
            typo_rate: Probability of typo per eligible character (defaults to profile's rate).
            window_title: Optional window title to focus before typing.
            progress_callback: Optional callback(current_index, total_chars, current_char).

        Returns:
            Dictionary with typing statistics (chars_typed, typos_corrected, elapsed_seconds, actual_wpm).
        """
        ensure_interactive_desktop()
        if not text:
            return {"chars_typed": 0, "typos_corrected": 0, "elapsed_seconds": 0.0, "actual_wpm": 0.0}

        if window_title:
            focused = focus_window(window_title)
            if focused:
                time.sleep(0.25)

        target_wpm = wpm or self.profile.target_wpm
        # 1 word = 5 characters standard
        base_char_delay = 60.0 / (target_wpm * 5.0)

        effective_typo_rate = (
            typo_rate if typo_rate is not None
            else (self.profile.typo_probability if introduce_typos else 0.0)
        )

        start_time = time.time()
        total_chars = len(text)
        typos_count = 0
        consecutive_chars_since_pause = 0

        for idx, char in enumerate(text):
            if progress_callback:
                progress_callback(idx + 1, total_chars, char)

            # Check if we should simulate an occasional typo
            can_typo = (
                introduce_typos
                and effective_typo_rate > 0
                and char.isalnum()
                and idx > 0
                and idx < total_chars - 1
            )

            if can_typo and random.random() < effective_typo_rate:
                adjacent_char = get_adjacent_typo(char)
                if adjacent_char:
                    # 1. Type the wrong key
                    dwell = self._calc_dwell_time() if human_like else 0.03
                    pyautogui.write(adjacent_char)
                    typos_count += 1

                    # 2. Hesitation / reaction time realizing the mistake
                    realize_sec = (self.profile.typo_realize_delay_ms / 1000.0) if human_like else 0.15
                    time.sleep(max(0.08, random.gauss(realize_sec, realize_sec * 0.2)))

                    # 3. Press Backspace to erase typo
                    press_single_key("backspace", dwell)

                    # 4. Brief pause before typing the correct key
                    correct_sec = (self.profile.typo_correct_delay_ms / 1000.0) if human_like else 0.08
                    time.sleep(max(0.05, random.gauss(correct_sec, correct_sec * 0.2)))

            # Type the target character
            if char == "\n":
                press_single_key("enter", self._calc_dwell_time() if human_like else 0.04)
            elif char == "\t":
                press_single_key("tab", self._calc_dwell_time() if human_like else 0.04)
            else:
                pyautogui.write(char)

            consecutive_chars_since_pause += 1

            if not human_like:
                time.sleep(base_char_delay)
                continue

            # Calculate natural pauses and micro-intervals
            char_delay = self._calc_char_delay(base_char_delay)

            # Punctuation pauses (end of sentence: . ! ?)
            if char in ".!?":
                sentence_pause = self.profile.sentence_pause_ms / 1000.0
                time.sleep(random.gauss(sentence_pause, sentence_pause * 0.2))
                consecutive_chars_since_pause = 0

            # Clause pauses (, ; : -)
            elif char in ",;:-":
                clause_pause = self.profile.clause_pause_ms / 1000.0
                time.sleep(random.gauss(clause_pause, clause_pause * 0.2))
                consecutive_chars_since_pause = 0

            # Space / word boundary
            elif char == " ":
                space_delay = char_delay * self.profile.space_pause_mult
                time.sleep(max(0.04, random.gauss(space_delay, space_delay * 0.15)))

                # Occasional cognitive thinking pause (every 18-35 words)
                if consecutive_chars_since_pause > random.randint(80, 160):
                    think_pause = random.uniform(0.35, 0.75)
                    time.sleep(think_pause)
                    consecutive_chars_since_pause = 0

            # Newline pause
            elif char == "\n":
                line_pause = (self.profile.sentence_pause_ms * 1.2) / 1000.0
                time.sleep(random.gauss(line_pause, line_pause * 0.2))
                consecutive_chars_since_pause = 0

            # Tricky characters (brackets, numbers, symbols)
            elif not char.isalnum():
                time.sleep(char_delay * self.profile.symbol_pause_mult)

            # Normal letter / digit
            else:
                time.sleep(char_delay)

        elapsed = time.time() - start_time
        actual_wpm = round(((total_chars / 5.0) / (elapsed / 60.0)), 1) if elapsed > 0 else 0.0

        return {
            "chars_typed": total_chars,
            "typos_corrected": typos_count,
            "elapsed_seconds": round(elapsed, 2),
            "actual_wpm": actual_wpm,
        }
