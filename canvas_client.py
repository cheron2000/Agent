"""canvas_client.py - Client helper and CLI to interact with the running AI Parallel Desktop Canvas."""

import json
import sys
import requests
from typing import Any, Dict, Optional

BASE_URL = "http://127.0.0.1:8765"


class CanvasClient:
    """Client for controlling the AI Parallel Desktop Canvas (Desktop 2)."""

    def __init__(self, base_url: str = BASE_URL):
        self.base_url = base_url

    def is_alive(self) -> bool:
        try:
            r = requests.get(f"{self.base_url}/health", timeout=2.0)
            return r.status_code == 200
        except Exception:
            return False

    def status(self) -> Dict[str, Any]:
        return requests.get(f"{self.base_url}/status", timeout=5.0).json()

    def navigate(self, url: str) -> Dict[str, Any]:
        return requests.post(f"{self.base_url}/navigate", json={"url": url}, timeout=15.0).json()

    def move(self, x: int, y: int, duration: float = 0.3) -> Dict[str, Any]:
        return requests.post(
            f"{self.base_url}/move",
            json={"x": x, "y": y, "duration": duration},
            timeout=5.0,
        ).json()

    def click(self, x: int, y: int, button: str = "left") -> Dict[str, Any]:
        return requests.post(
            f"{self.base_url}/click",
            json={"x": x, "y": y, "button": button},
            timeout=5.0,
        ).json()

    def type_text(self, text: str, delay: float = 0.04) -> Dict[str, Any]:
        return requests.post(
            f"{self.base_url}/type",
            json={"text": text, "delay": delay},
            timeout=10.0,
        ).json()

    def press(self, key: str) -> Dict[str, Any]:
        return requests.post(f"{self.base_url}/press", json={"key": key}, timeout=5.0).json()

    def scroll(self, delta_y: int) -> Dict[str, Any]:
        return requests.post(f"{self.base_url}/scroll", json={"delta_y": delta_y}, timeout=5.0).json()

    def set_hud_status(self, message: str) -> Dict[str, Any]:
        return requests.post(
            f"{self.base_url}/status_hud",
            json={"message": message},
            timeout=5.0,
        ).json()

    def capture(self) -> Dict[str, Any]:
        return requests.get(f"{self.base_url}/capture", timeout=10.0).json()

    def ocr(self, detailed: bool = False) -> Dict[str, Any]:
        return requests.get(f"{self.base_url}/ocr", params={"detailed": detailed}, timeout=15.0).json()

    def order_chocolate(self, item: str = "KitKat") -> Dict[str, Any]:
        return requests.post(
            f"{self.base_url}/order_chocolate",
            params={"item": item},
            timeout=40.0,
        ).json()


if __name__ == "__main__":
    client = CanvasClient()
    if not client.is_alive():
        print("[ERROR] AI Parallel Desktop Canvas server is not running on port 8765.")
        print("Launch it first with: python parallel_desktop_server.py")
        sys.exit(1)

    args = sys.argv[1:]
    if not args:
        print(json.dumps(client.status(), indent=2))
        sys.exit(0)

    cmd = args[0].lower()
    if cmd == "status":
        print(json.dumps(client.status(), indent=2))
    elif cmd == "navigate" and len(args) > 1:
        print(json.dumps(client.navigate(args[1]), indent=2))
    elif cmd == "move" and len(args) > 2:
        print(json.dumps(client.move(int(args[1]), int(args[2])), indent=2))
    elif cmd == "click" and len(args) > 2:
        print(json.dumps(client.click(int(args[1]), int(args[2])), indent=2))
    elif cmd == "type" and len(args) > 1:
        print(json.dumps(client.type_text(" ".join(args[1:])), indent=2))
    elif cmd == "scroll" and len(args) > 1:
        print(json.dumps(client.scroll(int(args[1])), indent=2))
    elif cmd == "order_chocolate":
        item = args[1] if len(args) > 1 else "KitKat"
        print(f"[INFO] Executing chocolate order for '{item}' inside AI canvas...")
        res = client.order_chocolate(item)
        print(json.dumps(res, indent=2))
    elif cmd == "ocr":
        print(json.dumps(client.ocr(), indent=2))
    else:
        print(f"Unknown command: {cmd}")
