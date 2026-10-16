"""api_client.py - Unified Client and CLI for the AI Master REST API.

Provides both an importable Python SDK and a terminal CLI to control all
Eyes, Hands, Canvas, and Automated Actions over HTTP endpoints.

Usage (Python):
    from api_client import AgentClient
    client = AgentClient()
    client.canvas.navigate("https://instagram.com")
    client.actions.login(username="xyzabcdef", password="...")

Usage (CLI):
    python api_client.py status
    python api_client.py eyes capture
    python api_client.py eyes ocr
    python api_client.py hands click --x 500 --y 300
    python api_client.py hands type "Hello World"
    python api_client.py canvas navigate "https://www.instagram.com/accounts/login/"
    python api_client.py actions login --user xyzabcdef --pass qwerty
"""

import argparse
import json
import os
import sys
from typing import Any, Dict, List, Optional
import requests

DEFAULT_SERVER_URL = "http://127.0.0.1:8765"


class EyesClient:
    def __init__(self, base_url: str):
        self.base_url = f"{base_url}/eyes"

    def capture(self, region: Optional[List[int]] = None, save: bool = True, include_base64: bool = False) -> Dict[str, Any]:
        return requests.post(f"{self.base_url}/capture", json={"region": region, "save": save, "include_base64": include_base64}, timeout=15.0).json()

    def ocr(self, region: Optional[List[int]] = None, detailed: bool = False) -> Dict[str, Any]:
        return requests.post(f"{self.base_url}/ocr", json={"region": region, "detailed": detailed}, timeout=20.0).json()

    def find(self, target: str) -> Dict[str, Any]:
        return requests.post(f"{self.base_url}/find", json={"target": target}, timeout=20.0).json()

    def screen_info(self) -> Dict[str, Any]:
        return requests.get(f"{self.base_url}/screen_info", timeout=5.0).json()

    def enhance_prompt(self, task: str, target_application: Optional[str] = None, context_hints: Optional[List[str]] = None) -> Dict[str, Any]:
        return requests.post(
            f"{self.base_url}/enhance_prompt",
            json={"task": task, "target_application": target_application, "context_hints": context_hints or []},
            timeout=10.0,
        ).json()

    def start_task(self, task_name: str = "task") -> Dict[str, Any]:
        return requests.post(f"{self.base_url}/task/start", json={"task_name": task_name}, timeout=5.0).json()

    def end_task(self) -> Dict[str, Any]:
        return requests.post(f"{self.base_url}/task/end", timeout=10.0).json()


class HandsClient:
    def __init__(self, base_url: str):
        self.base_url = f"{base_url}/hands"

    def click(self, x: Optional[int] = None, y: Optional[int] = None, button: str = "left", clicks: int = 1, window: Optional[str] = None) -> Dict[str, Any]:
        return requests.post(
            f"{self.base_url}/click",
            json={"x": x, "y": y, "button": button, "clicks": clicks, "window": window},
            timeout=10.0,
        ).json()

    def move(self, x: int, y: int, duration: float = 0.2, window: Optional[str] = None) -> Dict[str, Any]:
        return requests.post(
            f"{self.base_url}/move",
            json={"x": x, "y": y, "duration": duration, "window": window},
            timeout=10.0,
        ).json()

    def drag(self, x: int, y: int, duration: float = 0.5, button: str = "left", window: Optional[str] = None) -> Dict[str, Any]:
        return requests.post(
            f"{self.base_url}/drag",
            json={"x": x, "y": y, "duration": duration, "button": button, "window": window},
            timeout=10.0,
        ).json()

    def scroll(self, clicks: int, x: Optional[int] = None, y: Optional[int] = None, smooth: bool = True, horizontal: bool = False, window: Optional[str] = None) -> Dict[str, Any]:
        return requests.post(
            f"{self.base_url}/scroll",
            json={"clicks": clicks, "x": x, "y": y, "smooth": smooth, "horizontal": horizontal, "window": window},
            timeout=10.0,
        ).json()

    def type_text(self, text: str, wpm: Optional[float] = None, profile: str = "natural", introduce_typos: bool = False, window: Optional[str] = None) -> Dict[str, Any]:
        return requests.post(
            f"{self.base_url}/type",
            json={"text": text, "wpm": wpm, "profile": profile, "introduce_typos": introduce_typos, "window": window},
            timeout=30.0,
        ).json()

    def key(self, key_name: str, count: int = 1, dwell: float = 0.05, window: Optional[str] = None) -> Dict[str, Any]:
        return requests.post(
            f"{self.base_url}/key",
            json={"key": key_name, "count": count, "dwell": dwell, "window": window},
            timeout=10.0,
        ).json()

    def hotkey(self, keys: str, window: Optional[str] = None) -> Dict[str, Any]:
        return requests.post(
            f"{self.base_url}/hotkey",
            json={"keys": keys, "window": window},
            timeout=10.0,
        ).json()

    def paste(self, text: str, window: Optional[str] = None) -> Dict[str, Any]:
        return requests.post(
            f"{self.base_url}/paste",
            json={"text": text, "window": window},
            timeout=10.0,
        ).json()

    def windows(self) -> Dict[str, Any]:
        return requests.get(f"{self.base_url}/windows", timeout=10.0).json()

    def focus(self, title: str) -> Dict[str, Any]:
        return requests.post(f"{self.base_url}/focus", json={"title": title}, timeout=5.0).json()

    def status(self) -> Dict[str, Any]:
        return requests.get(f"{self.base_url}/status", timeout=5.0).json()


class CanvasClient:
    def __init__(self, base_url: str):
        self.base_url = f"{base_url}/canvas"

    def status(self) -> Dict[str, Any]:
        return requests.get(f"{self.base_url}/status", timeout=5.0).json()

    def navigate(self, url: str) -> Dict[str, Any]:
        return requests.post(f"{self.base_url}/navigate", json={"url": url}, timeout=25.0).json()

    def move(self, x: int, y: int, duration: float = 0.3) -> Dict[str, Any]:
        return requests.post(f"{self.base_url}/move", json={"x": x, "y": y, "duration": duration}, timeout=5.0).json()

    def click(self, x: int, y: int, button: str = "left") -> Dict[str, Any]:
        return requests.post(f"{self.base_url}/click", json={"x": x, "y": y, "button": button}, timeout=5.0).json()

    def type_text(self, text: str, delay: float = 0.04) -> Dict[str, Any]:
        return requests.post(f"{self.base_url}/type", json={"text": text, "delay": delay}, timeout=15.0).json()

    def press(self, key: str) -> Dict[str, Any]:
        return requests.post(f"{self.base_url}/press", json={"key": key}, timeout=5.0).json()

    def scroll(self, delta_y: int) -> Dict[str, Any]:
        return requests.post(f"{self.base_url}/scroll", json={"delta_y": delta_y}, timeout=5.0).json()

    def set_hud(self, message: str) -> Dict[str, Any]:
        return requests.post(f"{self.base_url}/hud", json={"message": message}, timeout=5.0).json()

    def capture(self) -> Dict[str, Any]:
        return requests.get(f"{self.base_url}/capture", timeout=10.0).json()

    def ocr(self, detailed: bool = False) -> Dict[str, Any]:
        return requests.get(f"{self.base_url}/ocr", params={"detailed": detailed}, timeout=20.0).json()


class ActionsClient:
    def __init__(self, base_url: str):
        self.base_url = f"{base_url}/actions"

    def login(
        self,
        username: str,
        password: str,
        url: str = "https://www.instagram.com/accounts/login/",
        platform: str = "instagram",
        username_selector: Optional[str] = None,
        password_selector: Optional[str] = None,
        submit_selector: Optional[str] = None,
    ) -> Dict[str, Any]:
        return requests.post(
            f"{self.base_url}/login",
            json={
                "url": url,
                "username": username,
                "password": password,
                "platform": platform,
                "username_selector": username_selector,
                "password_selector": password_selector,
                "submit_selector": submit_selector,
            },
            timeout=60.0,
        ).json()

    def order_chocolate(self, item: str = "KitKat") -> Dict[str, Any]:
        return requests.post(f"{self.base_url}/order_chocolate", params={"item": item}, timeout=45.0).json()


class AgentClient:
    """Master Client for interacting with the AI Master Server."""

    def __init__(self, base_url: str = DEFAULT_SERVER_URL):
        self.base_url = base_url
        self.eyes = EyesClient(base_url)
        self.hands = HandsClient(base_url)
        self.canvas = CanvasClient(base_url)
        self.actions = ActionsClient(base_url)

    def is_alive(self) -> bool:
        try:
            r = requests.get(f"{self.base_url}/health", timeout=2.0)
            return r.status_code == 200
        except Exception:
            return False

    def health(self) -> Dict[str, Any]:
        return requests.get(f"{self.base_url}/health", timeout=2.0).json()


# ── Terminal CLI ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(prog="api_client", description="AI Agent Master CLI: Perform any action via REST endpoints.")
    parser.add_argument("--server", dest="server_url", default=DEFAULT_SERVER_URL, help=f"Server URL (default: {DEFAULT_SERVER_URL})")

    subparsers = parser.add_subparsers(dest="domain", help="Endpoint domain")

    # Domain: eyes
    eyes_p = subparsers.add_parser("eyes", help="Eyes visual perception commands")
    eyes_sub = eyes_p.add_subparsers(dest="action", help="Eyes action")
    eyes_sub.add_parser("capture", help="Capture screenshot")
    ocr_p = eyes_sub.add_parser("ocr", help="Run OCR text extraction")
    ocr_p.add_argument("--detailed", action="store_true", help="Detailed word boxes")
    find_p = eyes_sub.add_parser("find", help="Find text on screen")
    find_p.add_argument("target", type=str, help="Text to search for")
    eyes_sub.add_parser("info", help="Get screen information")

    # Domain: hands
    hands_p = subparsers.add_parser("hands", help="Hands physical keyboard & mouse commands")
    hands_sub = hands_p.add_subparsers(dest="action", help="Hands action")
    click_p = hands_sub.add_parser("click", help="Click mouse")
    click_p.add_argument("--x", type=int, default=None)
    click_p.add_argument("--y", type=int, default=None)
    click_p.add_argument("--button", default="left", choices=["left", "right", "middle"])
    click_p.add_argument("--clicks", type=int, default=1)
    type_p = hands_sub.add_parser("type", help="Type text with human cadence")
    type_p.add_argument("text", type=str)
    type_p.add_argument("--wpm", type=float, default=None)
    key_p = hands_sub.add_parser("key", help="Press key")
    key_p.add_argument("name", type=str)
    hotkey_p = hands_sub.add_parser("hotkey", help="Trigger hotkey combination (e.g. 'win+r')")
    hotkey_p.add_argument("keys", type=str)
    paste_p = hands_sub.add_parser("paste", help="Paste text via clipboard")
    paste_p.add_argument("text", type=str)
    move_p = hands_sub.add_parser("move", help="Move cursor to (x, y)")
    move_p.add_argument("x", type=int)
    move_p.add_argument("y", type=int)
    scroll_p = hands_sub.add_parser("scroll", help="Scroll wheel")
    scroll_p.add_argument("clicks", type=int)
    focus_p = hands_sub.add_parser("focus", help="Focus window")
    focus_p.add_argument("title", type=str)
    hands_sub.add_parser("windows", help="List open windows")
    hands_sub.add_parser("status", help="Get Hands status")

    # Domain: canvas
    canvas_p = subparsers.add_parser("canvas", help="Parallel canvas (Desktop 2) commands")
    canvas_sub = canvas_p.add_subparsers(dest="action", help="Canvas action")
    canvas_sub.add_parser("status", help="Get canvas status")
    nav_p = canvas_sub.add_parser("navigate", help="Navigate to URL")
    nav_p.add_argument("url", type=str)
    c_click_p = canvas_sub.add_parser("click", help="Click inside canvas")
    c_click_p.add_argument("x", type=int)
    c_click_p.add_argument("y", type=int)
    c_type_p = canvas_sub.add_parser("type", help="Type inside canvas")
    c_type_p.add_argument("text", type=str)
    canvas_sub.add_parser("capture", help="Canvas screenshot")
    canvas_sub.add_parser("ocr", help="Canvas OCR")

    # Domain: actions
    act_p = subparsers.add_parser("actions", help="High-level automated action workflows")
    act_sub = act_p.add_subparsers(dest="action", help="Action workflow")
    login_p = act_sub.add_parser("login", help="Automated web login workflow")
    login_p.add_argument("--user", "-u", required=True, help="Username or email")
    login_p.add_argument("--pass", "-p", dest="password", required=True, help="Password")
    login_p.add_argument("--url", default="https://www.instagram.com/accounts/login/", help="Login URL")
    login_p.add_argument("--platform", default="instagram", help="Platform name")
    choc_p = act_sub.add_parser("chocolate", help="Order chocolate workflow")
    choc_p.add_argument("--item", default="KitKat", help="Chocolate item name")

    args = parser.parse_args()
    client = AgentClient(base_url=args.server_url)

    if not args.domain:
        print(f"[AI Agent Master Client] Server alive: {client.is_alive()} at {args.server_url}")
        parser.print_help()
        sys.exit(0)

    if not client.is_alive():
        print(f"[ERROR] Master server is not running at {args.server_url}.")
        print("Start it with: python agent_server.py")
        sys.exit(1)

    if args.domain == "eyes":
        if args.action == "capture":
            print(json.dumps(client.eyes.capture(), indent=2))
        elif args.action == "ocr":
            print(json.dumps(client.eyes.ocr(detailed=args.detailed), indent=2))
        elif args.action == "find":
            print(json.dumps(client.eyes.find(args.target), indent=2))
        elif args.action == "info":
            print(json.dumps(client.eyes.screen_info(), indent=2))

    elif args.domain == "hands":
        if args.action == "click":
            print(json.dumps(client.hands.click(x=args.x, y=args.y, button=args.button, clicks=args.clicks), indent=2))
        elif args.action == "type":
            print(json.dumps(client.hands.type_text(args.text, wpm=args.wpm), indent=2))
        elif args.action == "key":
            print(json.dumps(client.hands.key(args.name), indent=2))
        elif args.action == "hotkey":
            print(json.dumps(client.hands.hotkey(args.keys), indent=2))
        elif args.action == "paste":
            print(json.dumps(client.hands.paste(args.text), indent=2))
        elif args.action == "move":
            print(json.dumps(client.hands.move(args.x, args.y), indent=2))
        elif args.action == "scroll":
            print(json.dumps(client.hands.scroll(args.clicks), indent=2))
        elif args.action == "focus":
            print(json.dumps(client.hands.focus(args.title), indent=2))
        elif args.action == "windows":
            print(json.dumps(client.hands.windows(), indent=2))
        elif args.action == "status":
            print(json.dumps(client.hands.status(), indent=2))

    elif args.domain == "canvas":
        if args.action == "status":
            print(json.dumps(client.canvas.status(), indent=2))
        elif args.action == "navigate":
            print(json.dumps(client.canvas.navigate(args.url), indent=2))
        elif args.action == "click":
            print(json.dumps(client.canvas.click(args.x, args.y), indent=2))
        elif args.action == "type":
            print(json.dumps(client.canvas.type_text(args.text), indent=2))
        elif args.action == "capture":
            print(json.dumps(client.canvas.capture(), indent=2))
        elif args.action == "ocr":
            print(json.dumps(client.canvas.ocr(), indent=2))

    elif args.domain == "actions":
        if args.action == "login":
            print(f"[ACTION] Running Automated Login to {args.url} for user '{args.user}'...")
            res = client.actions.login(username=args.user, password=args.password, url=args.url, platform=args.platform)
            print(json.dumps(res, indent=2))
        elif args.action == "chocolate":
            print(f"[ACTION] Ordering {args.item}...")
            res = client.actions.order_chocolate(item=args.item)
            print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
