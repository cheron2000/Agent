import argparse
import os
import sys
from typing import List

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Ensure parent directory is in sys.path when executed directly as a script
if __package__ is None or not __package__:
    parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if parent_dir not in sys.path:
        sys.path.insert(0, parent_dir)
    __package__ = "agent_hands"

from .config import PROFILES
from .engine import TypingEngine
from .keyboard import execute_hotkey, fast_paste, press_single_key
from .mouse import click, double_click, right_click, scroll, move_to
from .windows import focus_window, get_active_window_title, list_windows


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agent-hands",
        description="AgentHands: Keyboard Hands for Any AI Agent with Human-Like Typing Simulation.",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # Command: type
    type_parser = subparsers.add_parser("type", help="Type text with realistic human cadence")
    type_parser.add_argument("text", type=str, help="Text to type")
    type_parser.add_argument("--wpm", type=float, default=None, help="Target Words Per Minute (e.g., 65)")
    type_parser.add_argument("--profile", type=str, default="natural", choices=list(PROFILES.keys()), help="Typing profile")
    type_parser.add_argument("--no-human", action="store_true", help="Disable human speed variance and micro-pauses")
    type_parser.add_argument("--typos", action="store_true", help="Simulate realistic typos and auto-correction")
    type_parser.add_argument("--typo-rate", type=float, default=0.015, help="Typo frequency per character (default: 0.015)")
    type_parser.add_argument("--window", "-w", type=str, default=None, help="Window title to focus before typing")

    # Command: key
    key_parser = subparsers.add_parser("key", help="Press a specific key")
    key_parser.add_argument("key", type=str, help="Key name (e.g., enter, tab, esc, backspace, up, down)")
    key_parser.add_argument("--count", "-c", type=int, default=1, help="Number of times to press")
    key_parser.add_argument("--dwell", type=float, default=0.05, help="Press dwell time in seconds")
    key_parser.add_argument("--window", "-w", type=str, default=None, help="Window title to focus before pressing")

    # Command: hotkey
    hotkey_parser = subparsers.add_parser("hotkey", help="Execute key combination / hotkey")
    hotkey_parser.add_argument("keys", type=str, help="Key combination (e.g. 'ctrl+c', 'alt+tab', 'win+r')")
    hotkey_parser.add_argument("--window", "-w", type=str, default=None, help="Window title to focus")

    # Command: paste
    paste_parser = subparsers.add_parser("paste", help="Instantly paste text block via clipboard")
    paste_parser.add_argument("text", type=str, help="Text to paste")
    paste_parser.add_argument("--window", "-w", type=str, default=None, help="Window title to focus")

    # Command: click
    click_parser = subparsers.add_parser("click", help="Click at (x, y) or current cursor position")
    click_parser.add_argument("--x", type=int, default=None, help="Target X coordinate")
    click_parser.add_argument("--y", type=int, default=None, help="Target Y coordinate")
    click_parser.add_argument("--button", "-b", type=str, default="left", choices=["left", "right", "middle"], help="Mouse button (default: left)")
    click_parser.add_argument("--double", "-d", action="store_true", help="Perform double click")
    click_parser.add_argument("--window", "-w", type=str, default=None, help="Window to focus before clicking")

    # Command: scroll
    scroll_parser = subparsers.add_parser("scroll", help="Scroll mouse wheel vertically or horizontally")
    scroll_parser.add_argument("clicks", type=int, help="Scroll amount (+ for UP, - for DOWN)")
    scroll_parser.add_argument("--x", type=int, default=None, help="X coordinate to hover before scrolling")
    scroll_parser.add_argument("--y", type=int, default=None, help="Y coordinate to hover before scrolling")
    scroll_parser.add_argument("--instant", action="store_true", help="Instant scroll without smooth steps")
    scroll_parser.add_argument("--horizontal", action="store_true", help="Scroll horizontally")
    scroll_parser.add_argument("--window", "-w", type=str, default=None, help="Window to focus before scrolling")

    # Command: move
    move_parser = subparsers.add_parser("move", help="Move cursor smoothly to (x, y)")
    move_parser.add_argument("x", type=int, help="Target X coordinate")
    move_parser.add_argument("y", type=int, help="Target Y coordinate")
    move_parser.add_argument("--duration", type=float, default=0.2, help="Travel duration in seconds")
    move_parser.add_argument("--window", "-w", type=str, default=None, help="Window to focus")

    # Command: windows
    subparsers.add_parser("windows", help="List open desktop windows")

    # Command: focus
    focus_parser = subparsers.add_parser("focus", help="Focus a desktop window")
    focus_parser.add_argument("title", type=str, help="Target window title substring")

    # Command: serve
    subparsers.add_parser("serve", help="Start AgentHands MCP Server (stdio transport)")

    # Command: status
    subparsers.add_parser("status", help="Show system status and active window")

    return parser


def main(args: List[str] = None):
    parser = build_parser()
    parsed = parser.parse_args(args)

    if not parsed.command:
        parser.print_help()
        sys.exit(0)

    if parsed.command == "type":
        engine = TypingEngine(profile=parsed.profile)
        stats = engine.type_text(
            text=parsed.text,
            wpm=parsed.wpm,
            human_like=not parsed.no_human,
            introduce_typos=parsed.typos,
            typo_rate=parsed.typo_rate,
            window_title=parsed.window,
        )
        print(f"[AgentHands] Typed {stats['chars_typed']} chars in {stats['elapsed_seconds']}s (~{stats['actual_wpm']} WPM). Typos corrected: {stats['typos_corrected']}.")

    elif parsed.command == "key":
        if parsed.window:
            focus_window(parsed.window)
        for _ in range(parsed.count):
            press_single_key(parsed.key, dwell_time=parsed.dwell)
        print(f"[AgentHands] Pressed '{parsed.key}' {parsed.count} time(s).")

    elif parsed.command == "hotkey":
        if parsed.window:
            focus_window(parsed.window)
        execute_hotkey(parsed.keys)
        print(f"[AgentHands] Triggered hotkey: {parsed.keys}")

    elif parsed.command == "paste":
        if parsed.window:
            focus_window(parsed.window)
        fast_paste(parsed.text)
        print(f"[AgentHands] Pasted {len(parsed.text)} characters.")

    elif parsed.command == "click":
        clicks = 2 if parsed.double else 1
        res = click(
            x=parsed.x,
            y=parsed.y,
            button=parsed.button,
            clicks=clicks,
            window_title=parsed.window,
        )
        print(f"[AgentHands] Clicked {res['button']} button ({res['clicks']}x) at ({res['x']}, {res['y']}).")

    elif parsed.command == "scroll":
        res = scroll(
            clicks=parsed.clicks,
            x=parsed.x,
            y=parsed.y,
            smooth=not parsed.instant,
            horizontal=parsed.horizontal,
            window_title=parsed.window,
        )
        print(f"[AgentHands] Scrolled {res['direction']} by {abs(res['clicks'])} units at ({res['x']}, {res['y']}).")

    elif parsed.command == "move":
        res = move_to(
            x=parsed.x,
            y=parsed.y,
            duration=parsed.duration,
            window_title=parsed.window,
        )
        print(f"[AgentHands] Moved cursor to ({res['x']}, {res['y']}).")

    elif parsed.command == "windows":
        windows = list_windows()
        print(f"Open Windows ({len(windows)}):")
        for w in windows:
            print(f" - [{w['hwnd']}] PID {w['pid']}: {w['title']}")

    elif parsed.command == "focus":
        success = focus_window(parsed.title)
        active = get_active_window_title()
        if success:
            print(f"[AgentHands] Focused window: '{active}'")
        else:
            print(f"[AgentHands] Could not find window matching: '{parsed.title}'")

    elif parsed.command == "serve":
        from .server import main as run_server
        print("[AgentHands] Starting MCP Server over stdio transport...", file=sys.stderr)
        run_server()

    elif parsed.command == "status":
        from .windows import get_active_window_title
        import pyautogui
        w, h = pyautogui.size()
        print(f"Screen Resolution: {w}x{h}")
        print(f"Active Window: {get_active_window_title()}")
        print(f"Available Profiles: {', '.join(PROFILES.keys())}")


if __name__ == "__main__":
    main()
