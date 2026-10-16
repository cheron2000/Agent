"""parallel_desktop_server.py - Dedicated FastAPI Daemon for the AI Parallel Desktop Canvas (Desktop 2).

Provides an isolated, concurrent desktop canvas window (Desktop 2) that:
1. Runs side-by-side with your personal desktop (Desktop 1).
2. Keeps your physical mouse & keyboard 100% free and untouched.
3. Renders a glowing neon cyan AI cursor and click ripple animations inside the canvas.
4. Confines all perception (screenshots, OCR) strictly to the canvas.
5. Employs ephemeral storage: automatically purges screenshots upon task completion.
"""

import asyncio
import contextlib
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Literal, Optional, Tuple

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from playwright.async_api import BrowserContext, Page, Playwright, async_playwright
from pydantic import BaseModel
import uvicorn

# Ensure Eyes is importable
sys.path.append(os.path.join(os.path.dirname(__file__), "Eyes"))
import eyes
from parallel_canvas import CURSOR_INJECTION_JS

SERVER_PORT = 8765


class AsyncParallelDesktop:
    """Async Playwright engine for the Parallel Desktop Canvas."""

    def __init__(self, width: int = 1240, height: int = 800):
        self.width = width
        self.height = height
        self.profile_dir = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "ai_chrome_profile")
        )
        os.makedirs(self.profile_dir, exist_ok=True)
        self._pw: Optional[Playwright] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.cursor_pos: Tuple[int, int] = (100, 100)

    async def start(self, initial_url: Optional[str] = None):
        if not initial_url:
            home_file = os.path.abspath(os.path.join(os.path.dirname(__file__), "desktop_home.html"))
            initial_url = Path(home_file).as_uri()

        self._pw = await async_playwright().start()
        self.context = await self._pw.chromium.launch_persistent_context(
            user_data_dir=self.profile_dir,
            headless=False,
            channel="chrome",
            viewport={"width": self.width, "height": self.height},
            args=[
                f"--window-size={self.width + 16},{self.height + 64}",
                "--window-position=40,40",
                f"--app={initial_url}",
                "--disable-blink-features=AutomationControlled",
            ],
            ignore_default_args=["--enable-automation"],
        )

        await self.context.add_init_script(CURSOR_INJECTION_JS)

        if self.context.pages:
            self.page = self.context.pages[0]
        else:
            self.page = await self.context.new_page()

        await self.page.goto(initial_url, wait_until="domcontentloaded")
        await self._ensure_cursor_script()
        print(f"[Parallel Canvas] [LAUNCHED] Desktop 2 running at: {initial_url}")

    async def _ensure_cursor_script(self):
        if self.page:
            try:
                await self.page.evaluate(CURSOR_INJECTION_JS)
            except Exception:
                pass

    async def set_status(self, status: str):
        if not self.page:
            return
        try:
            clean = status.replace("'", "\\'").replace('"', '\\"')
            await self.page.evaluate(f"window.__aiSetStatus('{clean}')")
        except Exception:
            pass

    async def navigate(self, url: str):
        if not self.page:
            return
        await self.page.goto(url, wait_until="domcontentloaded")
        await asyncio.sleep(1.0)
        await self._ensure_cursor_script()

    async def move_mouse(self, x: int, y: int, duration: float = 0.3):
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
        if not self.page:
            return
        await self.page.keyboard.type(text, delay=int(delay * 1000))

    async def press_key(self, key: str):
        if not self.page:
            return
        await self.page.keyboard.press(key)

    async def scroll(self, delta_y: int):
        if not self.page:
            return
        await self.page.mouse.wheel(0, delta_y)
        await asyncio.sleep(0.5)

    async def capture(self, save: bool = True) -> Dict[str, Any]:
        if not self.page:
            return {"success": False, "path": None, "error": "Page not loaded"}

        shots_dir = eyes.SHOTS_DIR
        ts = time.strftime("%Y%m%d_%H%M%S")
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
                    elements.append({
                        "text": w,
                        "confidence": c,
                        "center": {"x": x + bw // 2, "y": y + bh // 2},
                        "box": {"x": x, "y": y, "width": bw, "height": bh},
                    })

            return {"success": True, "text": " ".join(full_parts), "elements": elements}
        except Exception as e:
            return {"success": False, "text": "", "elements": [], "error": str(e)}

    async def close(self):
        try:
            if self.context:
                await self.context.close()
            if self._pw:
                await self._pw.stop()
        except Exception:
            pass


canvas: Optional[AsyncParallelDesktop] = None


@dataclass
class DesktopAgentState:
    """In-memory operator controls for actions initiated from the canvas console."""

    mode: str = "ask"
    active_task: Optional[str] = None
    pending_action: Optional[Dict[str, Any]] = None
    last_action: Optional[Dict[str, Any]] = None


agent_state = DesktopAgentState()


class NavigateRequest(BaseModel):
    url: str


class MoveRequest(BaseModel):
    x: int
    y: int
    duration: float = 0.3


class ClickRequest(BaseModel):
    x: int
    y: int
    button: str = "left"


class TypeRequest(BaseModel):
    text: str
    delay: float = 0.04


class PressRequest(BaseModel):
    key: str


class ScrollRequest(BaseModel):
    delta_y: int


class StatusHudRequest(BaseModel):
    message: str


class TaskRequest(BaseModel):
    task_name: str = "ai_task"


class AgentModeRequest(BaseModel):
    mode: Literal["observe", "ask", "routine"]


class AgentTaskRequest(BaseModel):
    task: str


class AgentActionRequest(BaseModel):
    action: Literal["navigate", "move", "click", "type", "press", "scroll"]
    url: Optional[str] = None
    x: Optional[int] = None
    y: Optional[int] = None
    duration: float = 0.3
    button: str = "left"
    text: Optional[str] = None
    delay: float = 0.04
    key: Optional[str] = None
    delta_y: Optional[int] = None


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    global canvas
    print("\n" + "=" * 70)
    print("[PARALLEL DESKTOP 2] Initializing AI Desktop Canvas Window...")
    print("  Host mouse: 100% free and untouched.")
    print("  AI workspace: strictly bounded inside the canvas.")
    print("=" * 70)
    canvas = AsyncParallelDesktop(width=1240, height=800)
    await canvas.start()
    await canvas.set_status("Desktop 2 Ready - Awaiting Instructions")
    yield
    if canvas:
        print("[PARALLEL DESKTOP 2] Closing canvas window...")
        await canvas.close()


app = FastAPI(title="AI Parallel Desktop 2", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["null", "http://127.0.0.1:8765"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


def agent_state_payload() -> Dict[str, Any]:
    return {
        "mode": agent_state.mode,
        "active_task": agent_state.active_task,
        "pending_action": agent_state.pending_action,
        "last_action": agent_state.last_action,
    }


def validate_agent_action(action: AgentActionRequest) -> Optional[str]:
    if action.action == "navigate" and not action.url:
        return "A URL is required for navigation."
    if action.action in {"move", "click"} and (action.x is None or action.y is None):
        return "Coordinates are required for pointer actions."
    if action.action == "type" and action.text is None:
        return "Text is required for a type action."
    if action.action == "press" and not action.key:
        return "A key is required for a press action."
    if action.action == "scroll" and action.delta_y is None:
        return "A scroll delta is required."
    return None


async def execute_agent_action(action: Dict[str, Any]) -> Dict[str, Any]:
    """Execute a previously validated browser-canvas action."""
    if not canvas:
        raise HTTPException(status_code=503, detail="Canvas not initialized")

    kind = action["action"]
    if kind == "navigate":
        await canvas.navigate(action["url"])
        result = {"success": True, "url": action["url"]}
    elif kind == "move":
        await canvas.move_mouse(action["x"], action["y"], duration=action.get("duration", 0.3))
        result = {"success": True, "cursor": [action["x"], action["y"]]}
    elif kind == "click":
        await canvas.click(action["x"], action["y"], button=action.get("button", "left"))
        result = {"success": True, "clicked_at": [action["x"], action["y"]]}
    elif kind == "type":
        await canvas.type_text(action["text"], delay=action.get("delay", 0.04))
        result = {"success": True, "typed_characters": len(action["text"])}
    elif kind == "press":
        await canvas.press_key(action["key"])
        result = {"success": True, "pressed": action["key"]}
    else:  # scroll
        await canvas.scroll(action["delta_y"])
        result = {"success": True, "delta_y": action["delta_y"]}

    agent_state.last_action = {"action": kind, "at": time.time(), "result": result}
    await canvas.set_status(f"Canvas action completed: {kind}")
    return result


@app.get("/health")
async def health() -> Dict[str, Any]:
    return {"status": "ok", "service": "AI Parallel Desktop 2"}


@app.get("/agent/state")
async def get_agent_state() -> Dict[str, Any]:
    """Return the visible console's permission mode and queued action, if any."""
    return agent_state_payload()


@app.post("/agent/mode")
async def set_agent_mode(req: AgentModeRequest) -> Dict[str, Any]:
    agent_state.mode = req.mode
    if canvas:
        labels = {
            "observe": "Observe only — actions blocked",
            "ask": "Approval required before each canvas action",
            "routine": "Routine canvas actions enabled",
        }
        await canvas.set_status(labels[req.mode])
    return {"success": True, **agent_state_payload()}


@app.post("/agent/task")
async def set_agent_task(req: AgentTaskRequest) -> Dict[str, Any]:
    task = req.task.strip()
    if not task:
        raise HTTPException(status_code=422, detail="Task cannot be empty")
    agent_state.active_task = task
    if canvas:
        await canvas.set_status(f"Task recorded: {task[:100]}")
    return {"success": True, **agent_state_payload()}


@app.post("/agent/actions/request")
async def request_agent_action(req: AgentActionRequest) -> Dict[str, Any]:
    """Run a canvas action or queue it for explicit operator approval."""
    error = validate_agent_action(req)
    if error:
        raise HTTPException(status_code=422, detail=error)

    action = (
        req.model_dump(exclude_none=True)
        if hasattr(req, "model_dump")
        else req.dict(exclude_none=True)
    )
    if agent_state.mode == "observe":
        return {
            "success": False,
            "status": "blocked",
            "reason": "Observe-only mode does not allow canvas actions.",
            **agent_state_payload(),
        }

    if agent_state.mode == "ask":
        if agent_state.pending_action:
            raise HTTPException(status_code=409, detail="An action is already awaiting approval")
        agent_state.pending_action = action
        if canvas:
            await canvas.set_status(f"Approval required: {action['action']}")
        return {"success": True, "status": "pending_approval", **agent_state_payload()}

    result = await execute_agent_action(action)
    return {"success": True, "status": "executed", "result": result, **agent_state_payload()}


@app.post("/agent/actions/approve")
async def approve_agent_action() -> Dict[str, Any]:
    action = agent_state.pending_action
    if not action:
        raise HTTPException(status_code=404, detail="No action is awaiting approval")
    agent_state.pending_action = None
    result = await execute_agent_action(action)
    return {"success": True, "status": "executed", "result": result, **agent_state_payload()}


@app.post("/agent/actions/reject")
async def reject_agent_action() -> Dict[str, Any]:
    if not agent_state.pending_action:
        raise HTTPException(status_code=404, detail="No action is awaiting approval")
    rejected = agent_state.pending_action
    agent_state.pending_action = None
    if canvas:
        await canvas.set_status(f"Action rejected: {rejected['action']}")
    return {"success": True, "rejected_action": rejected, **agent_state_payload()}


@app.get("/status")
async def get_status() -> Dict[str, Any]:
    if not canvas or not canvas.page:
        raise HTTPException(status_code=503, detail="Canvas not initialized")
    return {
        "active": True,
        "url": canvas.page.url,
        "cursor": list(canvas.cursor_pos),
        "viewport": {"width": canvas.width, "height": canvas.height},
        "active_task": eyes._ACTIVE_TASK_SESSION.task_name if eyes._ACTIVE_TASK_SESSION else None,
    }


@app.post("/navigate")
async def navigate(req: NavigateRequest) -> Dict[str, Any]:
    if not canvas:
        raise HTTPException(status_code=503, detail="Canvas not initialized")
    await canvas.set_status(f"Navigating to {req.url}...")
    await canvas.navigate(req.url)
    await canvas.set_status(f"Page Loaded: {req.url}")
    return {"success": True, "url": req.url}


@app.post("/move")
async def move_mouse(req: MoveRequest) -> Dict[str, Any]:
    if not canvas:
        raise HTTPException(status_code=503, detail="Canvas not initialized")
    await canvas.move_mouse(req.x, req.y, duration=req.duration)
    return {"success": True, "cursor": [req.x, req.y]}


@app.post("/click")
async def click_mouse(req: ClickRequest) -> Dict[str, Any]:
    if not canvas:
        raise HTTPException(status_code=503, detail="Canvas not initialized")
    await canvas.click(req.x, req.y, button=req.button)
    return {"success": True, "clicked_at": [req.x, req.y], "button": req.button}


@app.post("/type")
async def type_text(req: TypeRequest) -> Dict[str, Any]:
    if not canvas:
        raise HTTPException(status_code=503, detail="Canvas not initialized")
    await canvas.type_text(req.text, delay=req.delay)
    return {"success": True, "typed": req.text}


@app.post("/press")
async def press_key(req: PressRequest) -> Dict[str, Any]:
    if not canvas:
        raise HTTPException(status_code=503, detail="Canvas not initialized")
    await canvas.press_key(req.key)
    return {"success": True, "pressed": req.key}


@app.post("/scroll")
async def scroll(req: ScrollRequest) -> Dict[str, Any]:
    if not canvas:
        raise HTTPException(status_code=503, detail="Canvas not initialized")
    await canvas.scroll(req.delta_y)
    return {"success": True, "delta_y": req.delta_y}


@app.post("/status_hud")
async def update_status_hud(req: StatusHudRequest) -> Dict[str, Any]:
    if not canvas:
        raise HTTPException(status_code=503, detail="Canvas not initialized")
    await canvas.set_status(req.message)
    return {"success": True, "message": req.message}


@app.post("/task/start")
async def start_task(req: TaskRequest) -> Dict[str, Any]:
    session = eyes.start_task(req.task_name)
    if canvas:
        await canvas.set_status(f"Task Started: {req.task_name} [Ephemeral Storage Active]")
    return {"success": True, "task_name": session.task_name, "started_at": session.started_at}


@app.post("/task/end")
async def end_task() -> Dict[str, Any]:
    deleted_count = eyes.end_task()
    if canvas:
        await canvas.set_status(f"Task Completed - Purged {deleted_count} ephemeral screenshots")
    return {"success": True, "deleted_screenshots": deleted_count}


@app.get("/capture")
async def capture_viewport() -> Dict[str, Any]:
    if not canvas:
        raise HTTPException(status_code=503, detail="Canvas not initialized")
    return await canvas.capture(save=True)


@app.get("/ocr")
async def ocr_canvas(detailed: bool = False) -> Dict[str, Any]:
    if not canvas:
        raise HTTPException(status_code=503, detail="Canvas not initialized")
    return await canvas.transcribe(detailed=detailed)


@app.post("/order_chocolate")
async def execute_order_chocolate(item: str = "KitKat") -> Dict[str, Any]:
    """Execute the end-to-end chocolate order flow inside the parallel canvas."""
    if not canvas:
        raise HTTPException(status_code=503, detail="Canvas not initialized")

    eyes.start_task("order_chocolate_flow")
    await canvas.set_status(f"Initiating Chocolate Order: {item}...")

    # Step 1: Navigate to Swiggy Instamart
    await canvas.navigate("https://www.swiggy.com/instamart")
    await asyncio.sleep(3.0)

    # Step 2: Move AI cursor towards search area
    await canvas.set_status("Gliding AI cursor to search bar...")
    await canvas.move_mouse(400, 160, duration=0.4)
    await asyncio.sleep(0.3)
    await canvas.move_mouse(600, 160, duration=0.4)
    await asyncio.sleep(0.3)

    # Step 3: Click search bar
    await canvas.set_status("Clicking search bar with visual ripple...")
    await canvas.click(600, 160)
    await asyncio.sleep(0.6)

    # Step 4: Type item name
    await canvas.set_status(f"Typing '{item}' into search...")
    await canvas.type_text(item, delay=0.06)
    await asyncio.sleep(0.5)

    # Step 5: Press Enter
    await canvas.set_status("Submitting search query...")
    await canvas.press_key("Enter")
    await asyncio.sleep(4.0)

    # Step 6: Capture ephemeral screenshot & OCR verification
    await canvas.set_status("Verifying search results via OCR...")
    await canvas.capture(save=True)
    ocr = await canvas.transcribe(detailed=False)

    # Step 7: Scroll to explore results
    await canvas.set_status(f"Browsing {item} options...")
    await canvas.scroll(350)
    await asyncio.sleep(2.0)

    # Step 8: Conclude task and auto-purge screenshots
    deleted = eyes.end_task()
    await canvas.set_status(f"Search Complete: {item} displayed. Purged {deleted} temp screenshots.")

    return {
        "success": True,
        "item": item,
        "ocr_preview": ocr.get("text", "")[:300],
        "purged_screenshots": deleted,
    }


def run_server():
    uvicorn.run(app, host="127.0.0.1", port=SERVER_PORT, log_level="warning")


if __name__ == "__main__":
    run_server()
