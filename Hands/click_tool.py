#!/usr/bin/env python3
"""Standalone Click Tool for Hands.

Usage:
    python click_tool.py --x 500 --y 300
    python click_tool.py --x 500 --y 300 --button right
    python click_tool.py --double
    python click_tool.py --window "Google Chrome" --x 820 --y 969
"""

import argparse
import os
import sys

# Ensure agent_hands can be imported
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agent_hands.mouse import click


def main():
    parser = argparse.ArgumentParser(description="AgentHands Click Tool: Click anywhere on screen or in active window.")
    parser.add_argument("--x", type=int, default=None, help="Target X pixel coordinate (optional, defaults to current cursor position)")
    parser.add_argument("--y", type=int, default=None, help="Target Y pixel coordinate (optional, defaults to current cursor position)")
    parser.add_argument("--button", "-b", type=str, default="left", choices=["left", "right", "middle"], help="Mouse button to click (default: left)")
    parser.add_argument("--double", "-d", action="store_true", help="Perform a double click")
    parser.add_argument("--clicks", "-c", type=int, default=1, help="Number of clicks to perform (default: 1)")
    parser.add_argument("--interval", type=float, default=0.1, help="Delay between multiple clicks in seconds")
    parser.add_argument("--duration", type=float, default=0.15, help="Cursor travel duration before clicking")
    parser.add_argument("--window", "-w", type=str, default=None, help="Window title to focus before clicking")

    args = parser.parse_args()
    num_clicks = 2 if args.double else args.clicks

    res = click(
        x=args.x,
        y=args.y,
        button=args.button,
        clicks=num_clicks,
        interval=args.interval,
        duration=args.duration,
        window_title=args.window,
    )

    print(f"[Hands Tool: Click] Successfully performed {res['button']} click ({res['clicks']}x) at ({res['x']}, {res['y']}).")


if __name__ == "__main__":
    main()
