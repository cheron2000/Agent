"""Python client for the direct Windows Desktop Agent API."""

from typing import Any, Dict, Optional

import requests

BASE_URL = "http://127.0.0.1:8765"


class DesktopAgentClient:
    def __init__(self, base_url: str = BASE_URL):
        self.base_url = base_url.rstrip("/")

    def _get(self, path: str) -> Dict[str, Any]:
        return requests.get(f"{self.base_url}{path}", timeout=15).json()

    def _post(self, path: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return requests.post(f"{self.base_url}{path}", json=payload or {}, timeout=30).json()

    def health(self) -> Dict[str, Any]:
        return self._get("/health")

    def screen_info(self) -> Dict[str, Any]:
        return self._get("/eyes/info")

    def capture(self, save: bool = True) -> Dict[str, Any]:
        return self._post("/eyes/capture", {"save": save})

    def ocr(self, detailed: bool = False) -> Dict[str, Any]:
        return self._post("/eyes/ocr", {"detailed": detailed})

    def screen_map(self, columns: int = 12, rows: int = 8, min_confidence: int = 25) -> Dict[str, Any]:
        return self._post("/eyes/map", {"columns": columns, "rows": rows, "min_confidence": min_confidence})

    def find(self, target: str, min_confidence: int = 30) -> Dict[str, Any]:
        return self._post("/eyes/find", {"target": target, "min_confidence": min_confidence})

    def windows(self) -> Dict[str, Any]:
        return self._get("/hands/status")

    def focus(self, window_title: str) -> Dict[str, Any]:
        return self._post("/hands/focus", {"window_title": window_title})

    def move(self, x: int, y: int, duration: float = 0.2) -> Dict[str, Any]:
        return self._post("/hands/move", {"x": x, "y": y, "duration": duration})

    def click(self, x: int, y: int, button: str = "left", clicks: int = 1) -> Dict[str, Any]:
        return self._post("/hands/click", {"x": x, "y": y, "button": button, "clicks": clicks})

    def scroll(self, clicks: int, x: Optional[int] = None, y: Optional[int] = None) -> Dict[str, Any]:
        return self._post("/hands/scroll", {"clicks": clicks, "x": x, "y": y})

    def type_text(self, text: str, profile: str = "natural", typos: bool = False) -> Dict[str, Any]:
        return self._post("/hands/type", {"text": text, "profile": profile, "typos": typos})

    def press_key(self, key: str) -> Dict[str, Any]:
        return self._post("/hands/key", {"key": key})

    def hotkey(self, keys: list) -> Dict[str, Any]:
        return self._post("/hands/hotkey", {"keys": keys})

    def paste(self, text: str) -> Dict[str, Any]:
        return self._post("/hands/paste", {"text": text})
