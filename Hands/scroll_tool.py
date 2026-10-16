#!/usr/bin/env python3
"""Standalone Scroll Tool for Hands.

Usage:
    python scroll_tool.py --amount -5       # Scroll DOWN 5 units
    python scroll_tool.py --amount 5        # Scroll UP 5 units
    python scroll_tool.py --amount -10 --x 960 --y 540  # Scroll over center of screen
    python scroll_tool.py --amount -5 --window "Google Chrome"
    python scroll_tool.py --amount 3 --horizontal  # Scroll right
"""

import argparse
import os
import sys

# Ensure agent_hands can be imported
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agent_hands.mouse import scroll


def main():
    parser = argparse.ArgumentParser(description="AgentHands Scroll Tool: Scroll mouse wheel vertically or horizontally.")
    parser.add_argument("--amount", "-a", type=int, required=True, help="Scroll amount (+ for UP, - for DOWN)")
    parser.add_argument("--x", type=int, default=None, help="Optional X coordinate to hover over before scrolling")
    parser.add_argument("--y", type=int, default=None, help="Optional Y coordinate to hover over before scrolling")
    parser.add_argument("--instant", action="store_true", help="Perform instant scroll rather than smooth human-like scrolling")
    parser.add_argument("--horizontal", action="store_true", help="Scroll horizontally rather than vertically")
    parser.add_argument("--window", "-w", type=str, default=None, help="Window title to focus before scrolling")

    args = parser.parse_args()

    res = scroll(
        clicks=args.amount,
        x=args.x,
        y=args.y,
        smooth=not args.instant,
        horizontal=args.horizontal,
        window_title=args.window,
    )

    print(f"[Hands Tool: Scroll] Scrolled {res['direction']} by {abs(res['clicks'])} units at ({res['x']}, {res['y']}).")


if __name__ == "__main__":
    main()
