"""Python client for the direct Windows Desktop Agent API.

Provides authenticated HTTP client bindings with automatic token discovery.
"""

from contextlib import contextmanager
import os
from typing import Any, Dict, List, Literal, Optional

import requests

BASE_URL = "http://127.0.0.1:8765"


class DesktopAgentClient:
    """Client for the local authenticated Windows Desktop Agent REST API."""

    def __init__(self, base_url: str = BASE_URL, auth_token: Optional[str] = None):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()

        # Token auto-discovery: explicit -> env var -> .agent_token file
        token = auth_token or os.environ.get("AGENT_AUTH_TOKEN")
        if not token:
            for candidate in [".agent_token", os.path.join(os.path.dirname(__file__), ".agent_token")]:
                if os.path.exists(candidate):
                    try:
                        with open(candidate, "r", encoding="utf-8") as f:
                            token = f.read().strip()
                            if token:
                                break
                    except Exception:
                        pass

        if token:
            self.session.headers.update({"Authorization": f"Bearer {token}"})

    def _get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        resp = self.session.get(f"{self.base_url}{path}", params=params, timeout=15)
        resp.raise_for_status()
        return resp.json()

    def _post(self, path: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        resp = self.session.post(f"{self.base_url}{path}", json=payload or {}, timeout=30)
        resp.raise_for_status()
        return resp.json()

    # ── Context Manager for Tasks ────────────────────────────────────────────
    @contextmanager
    def task(self, task_name: str = "desktop_task"):
        """Context manager to auto-cleanup ephemeral screenshots upon completion."""
        self.start_task(task_name)
        try:
            yield self
        finally:
            self.end_task()

    # ── Service & Perception ─────────────────────────────────────────────────
    def health(self) -> Dict[str, Any]:
        """Check server health (unauthenticated)."""
        resp = requests.get(f"{self.base_url}/health", timeout=5)
        resp.raise_for_status()
        return resp.json()

    def screen_info(self) -> Dict[str, Any]:
        return self._get("/eyes/info")

    def capture(self, save: bool = True, include_base64: bool = False) -> Dict[str, Any]:
        return self._post("/eyes/capture", {"save": save, "include_base64": include_base64})

    def ocr(self, detailed: bool = False) -> Dict[str, Any]:
        return self._post("/eyes/ocr", {"detailed": detailed})

    def screen_map(self, columns: int = 12, rows: int = 8, min_confidence: int = 25) -> Dict[str, Any]:
        return self._post("/eyes/map", {"columns": columns, "rows": rows, "min_confidence": min_confidence})

    def find(self, target: str, min_confidence: int = 30) -> Dict[str, Any]:
        return self._post("/eyes/find", {"target": target, "min_confidence": min_confidence})

    def describe(self, prompt: Optional[str] = None) -> Dict[str, Any]:
        return self._post("/eyes/describe", {"prompt": prompt})

    def start_task(self, task_name: str = "desktop_task") -> Dict[str, Any]:
        return self._post("/eyes/task/start", {"task_name": task_name})

    def end_task(self) -> Dict[str, Any]:
        return self._post("/eyes/task/end")

    def observe(
        self,
        save_annotated: bool = True,
        max_elements: int = 100,
        annotate: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """Fetch unified observation with numbered UI elements for LLM grounding."""
        if annotate is not None:
            save_annotated = annotate
        return self._post("/eyes/observe", {"save_annotated": save_annotated, "max_elements": max_elements})

    def zoom(
        self,
        region: Optional[List[int]] = None,
        element_id: Optional[int] = None,
        scale: float = 3.0,
    ) -> Dict[str, Any]:
        """Zoom into a region or element ID with high-resolution OCR."""
        payload: Dict[str, Any] = {"scale": scale}
        if region is not None:
            payload["region"] = region
        if element_id is not None:
            payload["element_id"] = element_id
        return self._post("/eyes/zoom", payload)

    def wait_for(self, target: str, timeout_s: float = 5.0) -> Dict[str, Any]:
        """Poll the desktop until target text appears."""
        return self._post("/eyes/wait", {"target": target, "timeout_s": timeout_s})

    # ── Context Layer ────────────────────────────────────────────────────────
    def analyze_context(self, goal: Optional[str] = None) -> Dict[str, Any]:
        """Analyze current screen context, formulate situational rationale, and suggest next action."""
        return self._post("/context/analyze", {"goal": goal})


    # ── Physical Desktop Actions ─────────────────────────────────────────────
    def windows(self, include_windows: bool = True) -> Dict[str, Any]:
        return self._get("/hands/status", params={"include_windows": include_windows})

    def focus(self, window_title: str) -> Dict[str, Any]:
        return self._post("/hands/focus", {"window_title": window_title})

    def move(self, x: int, y: int, duration: float = 0.2) -> Dict[str, Any]:
        return self._post("/hands/move", {"x": x, "y": y, "duration": duration})

    def click(
        self,
        x: Optional[int] = None,
        y: Optional[int] = None,
        button: Literal["left", "right", "middle"] = "left",
        clicks: int = 1,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"button": button, "clicks": clicks}
        if x is not None and y is not None:
            payload["x"] = x
            payload["y"] = y
        return self._post("/hands/click", payload)

    def click_element(
        self,
        element_id: int,
        button: Literal["left", "right", "middle"] = "left",
        clicks: int = 1,
    ) -> Dict[str, Any]:
        """Click an element by its observation ID."""
        return self._post("/hands/click_element", {"element_id": element_id, "button": button, "clicks": clicks})


    def scroll(self, clicks: int, x: Optional[int] = None, y: Optional[int] = None) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"clicks": clicks}
        if x is not None and y is not None:
            payload["x"] = x
            payload["y"] = y
        return self._post("/hands/scroll", payload)

    def type_text(
        self,
        text: str,
        profile: Literal["natural", "fast", "careful", "coder"] = "natural",
        typos: bool = False,
    ) -> Dict[str, Any]:
        return self._post("/hands/type", {"text": text, "profile": profile, "typos": typos})

    def press_key(self, key: str) -> Dict[str, Any]:
        return self._post("/hands/key", {"key": key})

    def hotkey(self, keys: List[str]) -> Dict[str, Any]:
        return self._post("/hands/hotkey", {"keys": keys})

    def paste(self, text: str, restore_clipboard: bool = True) -> Dict[str, Any]:
        return self._post("/hands/paste", {"text": text, "restore_clipboard": restore_clipboard})
