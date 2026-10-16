"""Interactive Demonstration of AgentHands: Human-Like Typing Simulation.

Run this script to see AgentHands in action.
"""

import os
import sys
import time

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Ensure agent_hands can be imported when running demo directly
parent_dir = os.path.dirname(os.path.abspath(__file__))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from agent_hands.config import PROFILES
from agent_hands.engine import TypingEngine
from agent_hands.windows import get_active_window_title, list_windows


def main():
    print("=" * 70)
    print("🖐️  AgentHands: Universal Keyboard Hands for AI Agents")
    print("=" * 70)
    print("\nFeatures loaded:")
    print(" ✔️ Gaussian / Log-Normal Keystroke Cadence")
    print(" ✔️ Punctuation & Clause Micro-Pauses")
    print(" ✔️ QWERTY Adjacency Typo Simulation & Auto-Correction")
    print(" ✔️ Window Detection and Focusing")
    print(" ✔️ Model Context Protocol (MCP) Server for Any Agent")
    print("\nAvailable Typing Profiles:")
    for name, p in PROFILES.items():
        print(f"  • {name.upper():<10} -> Target {p.target_wpm} WPM (typo prob: {p.typo_probability * 100}%)")

    print("\nCurrent Desktop Active Window:", get_active_window_title() or "[None / Desktop]")

    demo_text = (
        "Hello! I am an AI agent equipped with AgentHands. "
        "Notice how my typing cadence fluctuates naturally, pausing briefly after sentences. "
        "If I make a typo, I notice it, press backspace, and correct it automatically!"
    )

    print("\n" + "-" * 70)
    print(f"Sample Demonstration Text:\n\"{demo_text}\"")
    print("-" * 70)
    print("\nStarting simulated test run in 3 seconds...")
    for i in range(3, 0, -1):
        print(f"  Starting in {i}...", end="\r", flush=True)
        time.sleep(1)
    print("  Typing simulation active!                                  \n")

    engine = TypingEngine(profile="natural")

    def progress_cb(current, total, char):
        pct = int((current / total) * 100)
        bar = "█" * (pct // 5) + "░" * (20 - (pct // 5))
        display_char = repr(char) if char in "\n\t " else char
        sys.stdout.write(f"\r  [{bar}] {pct:>3}% | Typing: {display_char:<5}")
        sys.stdout.flush()

    stats = engine.type_text(
        text=demo_text,
        wpm=68.0,
        human_like=True,
        introduce_typos=True,
        typo_rate=0.02,
        progress_callback=progress_cb,
    )

    print("\n\n" + "=" * 70)
    print("🎉 Typing Simulation Completed Successfully!")
    print(f" • Characters typed: {stats['chars_typed']}")
    print(f" • Realized Speed:   {stats['actual_wpm']} WPM")
    print(f" • Duration:         {stats['elapsed_seconds']} seconds")
    print(f" • Typos corrected:  {stats['typos_corrected']}")
    print("=" * 70)


if __name__ == "__main__":
    main()
