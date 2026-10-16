"""parallel_desktop_server.py - Primary FastAPI server for the Parallel AI Desktop Canvas.

Exposes HTTP endpoints for navigating, clicking, typing, capturing, and
managing ephemeral task sessions inside an isolated Playwright Chromium process.
Port: 8765.
"""

import asyncio
import json
import os
import sys
import uuid
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator
import uvicorn

ROOT = os.path.dirname(__file__)
sys.path.extend([os.path.join(ROOT, "Eyes")])

import eyes

from parallel_canvas import CURSOR_INJECTION_JS

SERVER_PORT = 8765

app = FastAPI(title="Parallel AI Desktop Canvas", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:8765", "http://localhost:8765"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Module-level canvas instance — populated on startup
canvas: Optional["AsyncParallelDesktop"] = None


# ── Async canvas implementation ───────────────────────────────────────────────

class AsyncParallelDesktop:
    """Async Playwright-based parallel desktop canvas for AI-driven browser automation."""

    def __init__(
        self,
        profile_dir: Optional[str] = None,
        width: int = 1240,
        height: int = 800,
    ):
        self.profile_dir = profile_dir or os.path.abspath(
            os.path.join(ROOT, "ai_chrome_profile")
        )
        os.makedirs(self.profile_dir, exist_ok=True)
        self.width = width
        self.height = height
        self.page = None
        self.context = None
        self._browser = None
        self.cursor_pos = (100, 100)

    async def start(self, initial_url: Optional[str] = None):
        """Launch the async parallel desktop window."""
        from playwright.async_api import async_playwright

        if not initial_url:
            home_file = os.path.abspath(os.path.join(ROOT, "desktop_home.html"))
            initial_url = f"file:///{home_file.replace(os.sep, '/')}"

        self._pw = await async_playwright().start()
        self.context = await self._pw.chromium.launch_persistent_context(
            user_data_dir=self.profile_dir,
            headless=False,
            viewport={"width": self.width, "height": self.height},
            args=[
                f"--window-size={self.width + 16},{self.height + 64}",
                "--window-position=40,40",
                f"--app={initial_url}",
                "--disable-blink-features=AutomationControlled",
            ],
            ignore_default_args=["--enable-automation"],
        )
        self.page = (
            self.context.pages[0] if self.context.pages else await self.context.new_page()
        )
        await self.page.goto(initial_url, wait_until="domcontentloaded")
        await self.context.add_init_script(CURSOR_INJECTION_JS)
        await self._ensure_cursor_script()

    async def set_status(self, status: str):
        """Update floating HUD status on the canvas in real time."""
        if not self.page:
            return
        try:
            safe = json.dumps(status)
            await self.page.evaluate(f"window.__aiSetStatus({safe})")
        except Exception:
            pass

    async def _ensure_cursor_script(self):
        try:
            await self.page.evaluate(CURSOR_INJECTION_JS)
        except Exception:
            pass

    async def navigate(self, url: str):
        """Navigate to URL inside the parallel canvas."""
        if self.page:
            await self.page.goto(url, wait_until="domcontentloaded")
            await asyncio.sleep(1.0)
            await self._ensure_cursor_script()

    async def move_mouse(self, x: int, y: int, duration: float = 0.3):
        """Glide the visual AI cursor to (x, y)."""
        if not self.page:
            return
        self.cursor_pos = (x, y)
        try:
            await self.page.evaluate(f"window.__aiMoveCursor({x}, {y})")
        except Exception:
            await self._ensure_cursor_script()
            try:
                await self.page.evaluate(f"window.__aiMoveCursor({x}, {y})")
            except Exception:
                pass
        await self.page.mouse.move(x, y)
        await asyncio.sleep(duration)

    async def click(self, x: int, y: int, button: str = "left"):
        """Perform a virtual click inside the canvas with visual ripple."""
        if not self.page:
            return
        await self.move_mouse(x, y, duration=0.25)
        try:
            await self.page.evaluate(f"window.__aiTriggerRipple({x}, {y})")
        except Exception:
            pass
        await self.page.mouse.click(x, y, button=button)
        await asyncio.sleep(0.3)

    async def type_text(self, text: str, delay: float = 0.04):
        """Type text with realistic keystrokes into the active canvas input."""
        if not self.page:
            return
        await self.page.keyboard.type(text, delay=int(delay * 1000))

    async def press_key(self, key: str):
        """Press a keyboard key inside the canvas."""
        if not self.page:
            return
        await self.page.keyboard.press(key)

    async def scroll(self, delta_y: int):
        """Scroll mouse wheel inside the canvas."""
        if not self.page:
            return
        await self.page.mouse.wheel(0, delta_y)
        await asyncio.sleep(0.5)

    async def capture(self, save: bool = True) -> Dict[str, Any]:
        """Capture screenshot from the canvas viewport."""
        if not self.page:
            return {"success": False, "path": None, "error": "Page not loaded"}

        shots_dir = eyes.SHOTS_DIR
        import time as _time

        ts = _time.strftime("%Y%m%d_%H%M%S")
        path = str(shots_dir / f"canvas_screen_{ts}.png")

        await self.page.screenshot(path=path)

        if eyes._ACTIVE_TASK_SESSION:
            eyes._ACTIVE_TASK_SESSION.add_screenshot(path)

        return {
            "success": True,
            "path": path,
            "width": self.width,
            "height": self.height,
            "error": None,
        }

    async def transcribe(self, detailed: bool = False) -> Dict[str, Any]:
        """Run OCR on the canvas viewport image."""
        cap = await self.capture(save=True)
        if not cap["success"]:
            return {"success": False, "text": "", "elements": []}

        try:
            import pytesseract
            from PIL import Image

            tess = eyes._find_tesseract()
            if tess:
                pytesseract.pytesseract.tesseract_cmd = tess

            img = Image.open(cap["path"])
            if not detailed:
                text = pytesseract.image_to_string(img).strip()
                return {"success": True, "text": text, "elements": []}

            data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
            elements = []
            full_parts = []
            n = len(data["text"])
            for i in range(n):
                w = data["text"][i].strip()
                c = int(data["conf"][i])
                if w and c > 25:
                    x = data["left"][i]
                    y = data["top"][i]
                    bw = data["width"][i]
                    bh = data["height"][i]
                    full_parts.append(w)
                    elements.append(
                        {
                            "text": w,
                            "confidence": c,
                            "center": {"x": x + bw // 2, "y": y + bh // 2},
                            "box": {"x": x, "y": y, "width": bw, "height": bh},
                        }
                    )

            return {"success": True, "text": " ".join(full_parts), "elements": elements}
        except Exception as e:
            return {"success": False, "text": "", "elements": [], "error": str(e)}

    async def close(self):
        """Close parallel canvas context."""
        try:
            if self.context:
                await self.context.close()
            if self._pw:
                await self._pw.stop()
        except Exception:
            pass


# ── Request models ────────────────────────────────────────────────────────────

class NavigateRequest(BaseModel):
    url: str = Field(min_length=1)


class MoveRequest(BaseModel):
    x: int
    y: int
    duration: float = Field(default=0.3, ge=0, le=5)

    @field_validator("x", mode="after")
    @classmethod
    def validate_x(cls, value: int) -> int:
        if value < 0 or value > 1240:
            raise ValueError("x must be between 0 and 1240")
        return value

    @field_validator("y", mode="after")
    @classmethod
    def validate_y(cls, value: int) -> int:
        if value < 0 or value > 800:
            raise ValueError("y must be between 0 and 800")
        return value


class ClickRequest(BaseModel):
    x: int
    y: int
    button: str = "left"

    @field_validator("x", mode="after")
    @classmethod
    def validate_x(cls, value: int) -> int:
        if value < 0 or value > 1240:
            raise ValueError("x must be between 0 and 1240")
        return value

    @field_validator("y", mode="after")
    @classmethod
    def validate_y(cls, value: int) -> int:
        if value < 0 or value > 800:
            raise ValueError("y must be between 0 and 800")
        return value


class TypeRequest(BaseModel):
    text: str


class KeyRequest(BaseModel):
    key: str = Field(min_length=1)


class ScrollRequest(BaseModel):
    delta_y: int = Field(ge=-5000, le=5000)


class StatusRequest(BaseModel):
    status: str


class TaskRequest(BaseModel):
    task_name: str = Field(default="canvas_task", min_length=1)


class OrderRequest(BaseModel):
    item: str = Field(default="dark chocolate", min_length=1)


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health")
async def health() -> Dict[str, str]:
    return {"status": "ok", "service": "Parallel AI Desktop Canvas"}


@app.post("/navigate")
async def navigate(req: NavigateRequest) -> Dict[str, Any]:
    if canvas is None or canvas.page is None:
        raise HTTPException(status_code=503, detail="Canvas not initialised")
    parsed = urlparse(req.url)
    if parsed.scheme not in {"http", "https"}:
        raise HTTPException(status_code=400, detail="Only http and https URLs are allowed")
    await canvas.navigate(req.url)
    return {"success": True, "url": req.url}


@app.post("/move")
async def move_mouse(req: MoveRequest) -> Dict[str, Any]:
    if canvas is None or canvas.page is None:
        raise HTTPException(status_code=503, detail="Canvas not initialised")
    await canvas.move_mouse(req.x, req.y, duration=req.duration)
    return {"success": True, "x": req.x, "y": req.y}


@app.post("/click")
async def click(req: ClickRequest) -> Dict[str, Any]:
    if canvas is None or canvas.page is None:
        raise HTTPException(status_code=503, detail="Canvas not initialised")
    await canvas.click(req.x, req.y, button=req.button)
    return {"success": True, "x": req.x, "y": req.y, "button": req.button}


@app.post("/type")
async def type_text(req: TypeRequest) -> Dict[str, Any]:
    if canvas is None or canvas.page is None:
        raise HTTPException(status_code=503, detail="Canvas not initialised")
    await canvas.type_text(req.text)
    return {"success": True, "characters": len(req.text)}


@app.post("/key")
async def press_key(req: KeyRequest) -> Dict[str, Any]:
    if canvas is None or canvas.page is None:
        raise HTTPException(status_code=503, detail="Canvas not initialised")
    await canvas.press_key(req.key)
    return {"success": True, "key": req.key}


@app.post("/scroll")
async def scroll(req: ScrollRequest) -> Dict[str, Any]:
    if canvas is None or canvas.page is None:
        raise HTTPException(status_code=503, detail="Canvas not initialised")
    await canvas.scroll(req.delta_y)
    return {"success": True, "delta_y": req.delta_y}


@app.post("/status")
async def set_status(req: StatusRequest) -> Dict[str, Any]:
    if canvas is None or canvas.page is None:
        raise HTTPException(status_code=503, detail="Canvas not initialised")
    await canvas.set_status(req.status)
    return {"success": True}


@app.post("/capture")
async def capture_viewport() -> Dict[str, Any]:
    if canvas is None or canvas.page is None:
        raise HTTPException(status_code=503, detail="Canvas not initialised")
    try:
        return await canvas.capture(save=True)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/ocr")
async def ocr_canvas() -> Dict[str, Any]:
    if canvas is None or canvas.page is None:
        raise HTTPException(status_code=503, detail="Canvas not initialised")
    try:
        return await canvas.transcribe(detailed=False)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/task/start")
async def start_task(req: TaskRequest) -> Dict[str, Any]:
    session = eyes.start_task(req.task_name)
    task_id = str(uuid.uuid4())
    return {
        "success": True,
        "task_name": session.task_name,
        "task_id": task_id,
        "started_at": session.started_at,
    }


@app.post("/task/end")
async def end_task() -> Dict[str, Any]:
    deleted = eyes.end_task()
    return {"success": True, "deleted_screenshots": deleted}


@app.post("/order_chocolate")
async def execute_order_chocolate(req: OrderRequest) -> Dict[str, Any]:
    """WARNING: This endpoint uses hard-coded pixel coordinates and time delays
    tuned for Swiggy Instamart's layout as of 2024. Layout changes, login walls,
    geolocation prompts, or consent dialogs will break it. It does NOT complete a
    purchase. For production use, replace coordinate-based interaction with DOM
    selectors."""
    if canvas is None or canvas.page is None:
        raise HTTPException(status_code=503, detail="Canvas not initialised")

    item = req.item
    eyes.start_task("order_chocolate")

    # Step 1: Navigate to Swiggy Instamart
    await canvas.navigate("https://www.swiggy.com/instamart")
    await asyncio.sleep(3.0)
    if "swiggy" not in canvas.page.url.lower():
        eyes.end_task()
        return {
            "success": False,
            "reason": "Navigation did not reach swiggy.com",
            "step_reached": "navigate",
            "item": item,
        }

    # Step 2: Move to search box
    try:
        await canvas.move_mouse(620, 120, duration=0.4)
        await canvas.set_status(f"Moving to search — {item}")
    except Exception as step_err:
        deleted = eyes.end_task()
        return {
            "success": False,
            "reason": str(step_err),
            "step_reached": "move_to_search",
            "item": item,
            "purged_screenshots": deleted,
        }

    # Step 3: Click search box
    try:
        await canvas.click(620, 120)
        await canvas.set_status("Clicked search box")
    except Exception as step_err:
        deleted = eyes.end_task()
        return {
            "success": False,
            "reason": str(step_err),
            "step_reached": "click_search",
            "item": item,
            "purged_screenshots": deleted,
        }

    # Step 4: Type item name
    try:
        await canvas.type_text(item)
        await canvas.set_status(f"Typed: {item}")
    except Exception as step_err:
        deleted = eyes.end_task()
        return {
            "success": False,
            "reason": str(step_err),
            "step_reached": "type_item",
            "item": item,
            "purged_screenshots": deleted,
        }

    # Step 5: Press Enter
    try:
        await canvas.press_key("Enter")
        await asyncio.sleep(2.0)
        await canvas.set_status("Searching…")
    except Exception as step_err:
        deleted = eyes.end_task()
        return {
            "success": False,
            "reason": str(step_err),
            "step_reached": "press_enter",
            "item": item,
            "purged_screenshots": deleted,
        }

    # Step 6: Capture and OCR results
    try:
        cap = await canvas.capture(save=True)
        ocr_result = await canvas.transcribe(detailed=False)
        ocr_preview = ocr_result.get("text", "")[:200]
        await canvas.set_status("OCR complete")
    except Exception as step_err:
        deleted = eyes.end_task()
        return {
            "success": False,
            "reason": str(step_err),
            "step_reached": "capture_ocr",
            "item": item,
            "purged_screenshots": deleted,
        }

    # Step 7: Scroll down to see more results
    try:
        await canvas.scroll(600)
        await asyncio.sleep(1.0)
        await canvas.set_status("Scrolled results")
    except Exception as step_err:
        deleted = eyes.end_task()
        return {
            "success": False,
            "reason": str(step_err),
            "step_reached": "scroll",
            "item": item,
            "purged_screenshots": deleted,
        }

    # Step 8: Cleanup
    try:
        deleted = eyes.end_task()
        await canvas.set_status("Task complete")
    except Exception as step_err:
        deleted = eyes.end_task()
        return {
            "success": False,
            "reason": str(step_err),
            "step_reached": "cleanup",
            "item": item,
            "purged_screenshots": deleted,
        }

    return {
        "success": True,
        "item": item,
        "ocr_preview": ocr_preview,
        "purged_screenshots": deleted,
    }


def run_server(port: int = SERVER_PORT) -> None:
    uvicorn.run(app, host="127.0.0.1", port=port)


if __name__ == "__main__":
    run_server()
