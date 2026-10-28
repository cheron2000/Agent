"""Parallel Desktop Server — Playwright-backed canvas automation REST API.

FastAPI service on port 8766 that drives an async Playwright browser canvas.
This is the canvas/Playwright counterpart to agent_server.py (which drives the
raw Windows desktop).  Endpoints mirror agent_server.py where applicable so that
clients can swap transports without changing their calling convention.
"""

import asyncio
import json
import logging
import os
import sys
import uuid
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, field_validator

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.extend([os.path.join(ROOT, "Eyes"), os.path.join(ROOT, "Hands")])

import eyes

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
_log_formatter = logging.Formatter(
    "%(asctime)s %(levelname)s [parallel_desktop_server] %(message)s"
)
_file_handler = logging.FileHandler(
    os.path.join(ROOT, "err.log"), encoding="utf-8"
)
_file_handler.setFormatter(_log_formatter)
_console_handler = logging.StreamHandler()
_console_handler.setFormatter(_log_formatter)
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
logger.addHandler(_file_handler)
logger.addHandler(_console_handler)

# ---------------------------------------------------------------------------
# Canvas implementation
# ---------------------------------------------------------------------------

class AsyncParallelDesktop:
    """Async Playwright browser canvas that exposes high-level automation helpers."""

    def __init__(self):
        self.page = None
        self._playwright = None
        self._browser = None

    async def start(self, headless: bool = False) -> None:
        from playwright.async_api import async_playwright
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=headless)
        self.page = await self._browser.new_page()
        logger.info("Playwright browser started (headless=%s)", headless)

    async def stop(self) -> None:
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        self.page = None
        logger.info("Playwright browser stopped")

    async def navigate(self, url: str, timeout_ms: int = 30_000) -> Dict[str, Any]:
        if self.page is None:
            raise RuntimeError("Canvas not started")
        await self.page.goto(url, timeout=timeout_ms)
        return {"success": True, "url": self.page.url}

    async def capture(self, save: bool = True) -> Dict[str, Any]:
        if self.page is None:
            raise RuntimeError("Canvas not started")
        path = None
        if save:
            screenshots_dir = os.path.join(ROOT, "Eyes", "screenshots")
            os.makedirs(screenshots_dir, exist_ok=True)
            path = os.path.join(screenshots_dir, f"canvas_{uuid.uuid4().hex[:8]}.png")
            await self.page.screenshot(path=path)
            # register with task session if active
            try:
                eyes._register_screenshot(path)
            except Exception:
                pass
        vp = self.page.viewport_size or {"width": 1240, "height": 800}
        return {
            "success": True,
            "path": path,
            "width": vp.get("width", 1240),
            "height": vp.get("height", 800),
            "error": None,
        }

    async def transcribe(self) -> Dict[str, Any]:
        if self.page is None:
            raise RuntimeError("Canvas not started")
        text = await self.page.evaluate("() => document.body ? document.body.innerText : ''")
        return {"success": True, "text": text or "", "elements": []}

    async def set_status(self, status: str) -> None:
        if self.page is None:
            return
        safe = json.dumps(status)
        await self.page.evaluate(f"window.__aiSetStatus && window.__aiSetStatus({safe})")

    async def move(self, x: int, y: int) -> None:
        if self.page is None:
            raise RuntimeError("Canvas not started")
        await self.page.mouse.move(x, y)

    async def click(self, x: int, y: int, button: str = "left") -> None:
        if self.page is None:
            raise RuntimeError("Canvas not started")
        await self.page.mouse.click(x, y, button=button)

    async def type_text(self, text: str, delay_ms: int = 50) -> None:
        if self.page is None:
            raise RuntimeError("Canvas not started")
        await self.page.keyboard.type(text, delay=delay_ms)

    async def key(self, key: str) -> None:
        if self.page is None:
            raise RuntimeError("Canvas not started")
        await self.page.keyboard.press(key)

    async def scroll(self, x: int, y: int, delta_x: int = 0, delta_y: int = -300) -> None:
        if self.page is None:
            raise RuntimeError("Canvas not started")
        await self.page.mouse.wheel(delta_x, delta_y)


# ---------------------------------------------------------------------------
# Global canvas instance
# ---------------------------------------------------------------------------
canvas: Optional[AsyncParallelDesktop] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global canvas
    canvas = AsyncParallelDesktop()
    yield
    if canvas:
        try:
            await canvas.stop()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Parallel Desktop Server",
    version="1.0.0",
    description="Playwright-backed canvas automation REST API",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Request/Response models
# ---------------------------------------------------------------------------

class NavigateRequest(BaseModel):
    url: str

class MoveRequest(BaseModel):
    x: int
    y: int

    @field_validator("x", mode="after")
    @classmethod
    def validate_x(cls, v):
        if v < 0 or v > 1240:
            raise ValueError("x must be between 0 and 1240")
        return v

    @field_validator("y", mode="after")
    @classmethod
    def validate_y(cls, v):
        if v < 0 or v > 800:
            raise ValueError("y must be between 0 and 800")
        return v

class ClickRequest(BaseModel):
    x: int
    y: int
    button: str = "left"

    @field_validator("x", mode="after")
    @classmethod
    def validate_x(cls, v):
        if v < 0 or v > 1240:
            raise ValueError("x must be between 0 and 1240")
        return v

    @field_validator("y", mode="after")
    @classmethod
    def validate_y(cls, v):
        if v < 0 or v > 800:
            raise ValueError("y must be between 0 and 800")
        return v

class TypeRequest(BaseModel):
    text: str
    delay_ms: int = 50

class KeyRequest(BaseModel):
    key: str

class ScrollRequest(BaseModel):
    x: int = 640
    y: int = 400
    delta_x: int = 0
    delta_y: int = -300

class StatusRequest(BaseModel):
    status: str

class TaskStartRequest(BaseModel):
    task_name: str = "canvas_task"

class OrderChocolateRequest(BaseModel):
    item: str = "dark chocolate"


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "canvas_ready": canvas is not None and canvas.page is not None,
        "version": "1.0.0",
    }


@app.post("/navigate")
async def navigate(req: NavigateRequest):
    if canvas is None or canvas.page is None:
        raise HTTPException(status_code=503, detail="Canvas not started")
    parsed = urlparse(req.url)
    if parsed.scheme not in {"http", "https"}:
        raise HTTPException(status_code=400, detail="Only http and https URLs are allowed")
    try:
        result = await canvas.navigate(req.url)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return result


@app.post("/move")
async def move(req: MoveRequest):
    if canvas is None or canvas.page is None:
        raise HTTPException(status_code=503, detail="Canvas not started")
    try:
        await canvas.move(req.x, req.y)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"success": True, "x": req.x, "y": req.y}


@app.post("/click")
async def click_canvas(req: ClickRequest):
    if canvas is None or canvas.page is None:
        raise HTTPException(status_code=503, detail="Canvas not started")
    try:
        await canvas.click(req.x, req.y, button=req.button)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"success": True, "x": req.x, "y": req.y, "button": req.button}


@app.post("/type")
async def type_text(req: TypeRequest):
    if canvas is None or canvas.page is None:
        raise HTTPException(status_code=503, detail="Canvas not started")
    try:
        await canvas.type_text(req.text, delay_ms=req.delay_ms)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"success": True, "text": req.text}


@app.post("/key")
async def press_key(req: KeyRequest):
    if canvas is None or canvas.page is None:
        raise HTTPException(status_code=503, detail="Canvas not started")
    try:
        await canvas.key(req.key)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"success": True, "key": req.key}


@app.post("/scroll")
async def scroll(req: ScrollRequest):
    if canvas is None or canvas.page is None:
        raise HTTPException(status_code=503, detail="Canvas not started")
    try:
        await canvas.scroll(req.x, req.y, req.delta_x, req.delta_y)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"success": True}


@app.post("/status")
async def set_status(req: StatusRequest):
    if canvas is None or canvas.page is None:
        raise HTTPException(status_code=503, detail="Canvas not started")
    try:
        await canvas.set_status(req.status)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"success": True, "status": req.status}


@app.post("/capture")
async def capture_viewport():
    if canvas is None or canvas.page is None:
        raise HTTPException(status_code=503, detail="Canvas not started")
    try:
        return await canvas.capture(save=True)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/ocr")
async def ocr_canvas():
    if canvas is None or canvas.page is None:
        raise HTTPException(status_code=503, detail="Canvas not started")
    try:
        return await canvas.transcribe()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/task/start")
async def start_task(req: TaskStartRequest):
    session = eyes.start_task(req.task_name)
    task_id = str(uuid.uuid4())
    return {
        "success": True,
        "task_name": session.task_name,
        "task_id": task_id,
        "started_at": getattr(session, "started_at", None),
    }


@app.post("/task/end")
async def end_task():
    deleted = eyes.end_task()
    return {"success": True, "deleted_screenshots": deleted if isinstance(deleted, int) else 0}


@app.post("/order_chocolate")
async def execute_order_chocolate(req: OrderChocolateRequest):
    """WARNING: This endpoint uses hard-coded pixel coordinates and time delays tuned for
    Swiggy Instamart's layout as of 2024. Layout changes, login walls, geolocation prompts,
    or consent dialogs will break it. It does NOT complete a purchase. For production use,
    replace coordinate-based interaction with DOM selectors."""

    if canvas is None or canvas.page is None:
        raise HTTPException(status_code=503, detail="Canvas not started")

    item = req.item
    eyes.start_task("order_chocolate")

    # Step 1: Navigate
    try:
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
    except Exception as step_err:
        eyes.end_task()
        return {"success": False, "reason": str(step_err), "step_reached": "navigate", "item": item, "ocr_preview": ""}

    # Step 2: Move to search
    try:
        await canvas.move(620, 120)
    except Exception as step_err:
        eyes.end_task()
        return {"success": False, "reason": str(step_err), "step_reached": "move_to_search", "item": item, "ocr_preview": ""}

    # Step 3: Click search
    try:
        await canvas.click(620, 120)
        await asyncio.sleep(1.0)
    except Exception as step_err:
        eyes.end_task()
        return {"success": False, "reason": str(step_err), "step_reached": "click_search", "item": item, "ocr_preview": ""}

    # Step 4: Type item
    try:
        await canvas.type_text(item)
    except Exception as step_err:
        eyes.end_task()
        return {"success": False, "reason": str(step_err), "step_reached": "type_item", "item": item, "ocr_preview": ""}

    # Step 5: Press Enter
    try:
        await canvas.key("Enter")
        await asyncio.sleep(2.0)
    except Exception as step_err:
        eyes.end_task()
        return {"success": False, "reason": str(step_err), "step_reached": "press_enter", "item": item, "ocr_preview": ""}

    # Step 6: Capture OCR
    ocr_text = ""
    try:
        ocr_result = await canvas.transcribe()
        ocr_text = ocr_result.get("text", "")
    except Exception as step_err:
        eyes.end_task()
        return {"success": False, "reason": str(step_err), "step_reached": "capture_ocr", "item": item, "ocr_preview": ""}

    # Step 7: Scroll results
    try:
        await canvas.scroll(620, 400, 0, -300)
    except Exception as step_err:
        eyes.end_task()
        return {"success": False, "reason": str(step_err), "step_reached": "scroll", "item": item, "ocr_preview": ocr_text[:200]}

    # Step 8: Cleanup
    try:
        deleted = eyes.end_task()
    except Exception as step_err:
        return {"success": False, "reason": str(step_err), "step_reached": "cleanup", "item": item, "ocr_preview": ocr_text[:200]}

    return {
        "success": True,
        "item": item,
        "ocr_preview": ocr_text[:500],
        "purged_screenshots": deleted if isinstance(deleted, int) else 0,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("parallel_desktop_server:app", host="127.0.0.1", port=8766, reload=False)
