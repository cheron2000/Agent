"""agent_server.py - Unified Master REST API for AI Agent Hands, Eyes, Canvas & Actions.

Exposes every single capability across the entire system as cleanly structured HTTP endpoints:
- /eyes/*     : Full screen perception, OCR, element grounding, prompt enhancement, ephemeral tasks.
- /hands/*    : Physical OS mouse & keyboard automation with human cadence, window control.
- /canvas/*   : Parallel isolated Chromium desktop (Desktop 2) with glowing AI cursor & click ripples.
- /native/*   : Native PyQt6 canvas workspace bounds & state.
- /actions/*  : High-level automated workflows (web login, order food, search, etc.).

Swagger UI Documentation: http://127.0.0.1:8765/docs
"""

import asyncio
import contextlib
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Ensure Eyes and Hands are importable
sys.path.extend([
    os.path.join(os.path.dirname(__file__), "Eyes"),
    os.path.join(os.path.dirname(__file__), "Hands"),
    os.path.dirname(__file__),
])

from fastapi import FastAPI, HTTPException, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from playwright.async_api import BrowserContext, Page, Playwright, async_playwright
from pydantic import BaseModel, Field
import uvicorn

import eyes
from prompt_enhancer import PromptEnhancer
import agent_hands.mouse as hands_mouse
import agent_hands.keyboard as hands_keyboard
from agent_hands.engine import TypingEngine
from agent_hands.windows import focus_window, get_active_window_title, list_windows
from agent_hands.config import PROFILES
from canvas_desktop import CANVAS_STATE_FILE, get_canvas_bounds
from parallel_canvas import CURSOR_INJECTION_JS

SERVER_PORT = 8765


# ── Parallel Canvas Desktop 2 Engine ──────────────────────────────────────────

class AsyncParallelDesktop:
    """Async Playwright engine for the Parallel Desktop Canvas (Desktop 2)."""

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

        if self._pw is None:
            self._pw = await async_playwright().start()

        if self.context is None:
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
        print(f"[Parallel Canvas] [READY] Running at: {initial_url}")

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
        if not url.startswith("http://") and not url.startswith("https://") and not url.startswith("file:///"):
            url = "https://" + url
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
        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:19]
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
        self.context = None
        self.page = None
        self._pw = None


canvas: Optional[AsyncParallelDesktop] = None


async def get_canvas() -> AsyncParallelDesktop:
    global canvas
    if canvas is None:
        canvas = AsyncParallelDesktop(width=1240, height=800)
        await canvas.start()
    elif canvas.page is None or canvas.context is None:
        await canvas.start()
    return canvas


# ── Lifespan Context Manager ──────────────────────────────────────────────────

@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    global canvas
    print("=" * 75)
    print("🚀 [AI MASTER SERVER] Starting Unified REST API Daemon on port", SERVER_PORT)
    print("   Endpoints: /eyes/*, /hands/*, /canvas/*, /native/*, /actions/*")
    print("   Interactive Swagger UI: http://127.0.0.1:8765/docs")
    print("=" * 75)
    canvas = AsyncParallelDesktop(width=1240, height=800)
    try:
        await canvas.start()
        await canvas.set_status("AI Master Server Ready — Awaiting Instructions")
    except Exception as e:
        print(f"[AI Master Server] Note on canvas startup: {e}")
    yield
    if canvas:
        print("[AI Master Server] Closing canvas...")
        await canvas.close()


app = FastAPI(
    title="AI Agent Master REST API",
    description="Unified action & perception endpoints for Eyes vision, Hands keyboard/mouse, Parallel Desktop Canvas, and Automated Workflows.",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ═════════════════════════════════════════════════════════════════════════════
# 1. EYES ROUTER (Visual Perception & Screen Grounding)
# ═════════════════════════════════════════════════════════════════════════════

eyes_router = APIRouter(prefix="/eyes", tags=["Eyes (Vision Engine)"])


class EyesCaptureRequest(BaseModel):
    region: Optional[List[int]] = Field(None, description="[x, y, width, height] or null for full screen")
    save: bool = Field(True, description="Save screenshot file to disk")
    include_base64: bool = Field(False, description="Include base64 encoded image data")


class EyesOCRRequest(BaseModel):
    region: Optional[List[int]] = Field(None, description="[x, y, width, height] or null")
    detailed: bool = Field(False, description="Return word bounding boxes and confidence")


class EyesFindRequest(BaseModel):
    target: str = Field(..., description="Text or UI element label to search for on screen")


class EyesPromptEnhanceRequest(BaseModel):
    task: str = Field(..., description="Raw user prompt or goal")
    target_application: Optional[str] = Field(None, description="Target application name")
    context_hints: Optional[List[str]] = Field(None, description="Helpful contextual hints")


class EyesTaskRequest(BaseModel):
    task_name: str = Field("ai_task", description="Task session name for ephemeral screenshots")


@eyes_router.post("/capture", summary="Capture screenshot of screen or region")
def eyes_capture(req: EyesCaptureRequest) -> Dict[str, Any]:
    region = tuple(req.region) if req.region and len(req.region) == 4 else None
    return eyes.capture(region=region, save=req.save, include_base64=req.include_base64)


@eyes_router.post("/ocr", summary="Run OCR to extract text from screen")
def eyes_ocr(req: EyesOCRRequest) -> Dict[str, Any]:
    region = tuple(req.region) if req.region and len(req.region) == 4 else None
    return eyes.read_text(region=region, detailed=req.detailed)


@eyes_router.post("/find", summary="Locate text or UI element coordinates on screen")
def eyes_find(req: EyesFindRequest) -> Dict[str, Any]:
    return eyes.find_on_screen(req.target)


@eyes_router.get("/screen_info", summary="Get screen resolution & cursor position")
def eyes_screen_info() -> Dict[str, Any]:
    return eyes.get_screen_info()


@eyes_router.post("/enhance_prompt", summary="Enhance a raw user prompt into grounded visual steps")
def eyes_enhance_prompt(req: EyesPromptEnhanceRequest) -> Dict[str, Any]:
    enhancer = PromptEnhancer()
    return enhancer.enhance_task_prompt(
        raw_task=req.task,
        target_application=req.target_application,
        context_hints=req.context_hints or [],
    )


@eyes_router.post("/task/start", summary="Start ephemeral task session (screenshots auto-purge on end)")
def eyes_start_task(req: EyesTaskRequest) -> Dict[str, Any]:
    session = eyes.start_task(req.task_name)
    return {"success": True, "task_name": session.task_name, "started_at": session.started_at}


@eyes_router.post("/task/end", summary="End ephemeral task session and purge all screenshots")
def eyes_end_task() -> Dict[str, Any]:
    deleted = eyes.end_task()
    return {"success": True, "deleted_screenshots": deleted}


app.include_router(eyes_router)


# ═════════════════════════════════════════════════════════════════════════════
# 2. HANDS ROUTER (Physical OS Mouse & Keyboard Automation)
# ═════════════════════════════════════════════════════════════════════════════

hands_router = APIRouter(prefix="/hands", tags=["Hands (Keyboard & Mouse Automation)"])


class HandsClickRequest(BaseModel):
    x: Optional[int] = Field(None, description="Target X coordinate")
    y: Optional[int] = Field(None, description="Target Y coordinate")
    button: str = Field("left", description="'left', 'right', or 'middle'")
    clicks: int = Field(1, description="Number of clicks (1 for single, 2 for double)")
    interval: float = Field(0.1, description="Delay between clicks in seconds")
    duration: float = Field(0.15, description="Cursor travel duration")
    window: Optional[str] = Field(None, description="Window title to focus first")


class HandsMoveRequest(BaseModel):
    x: int = Field(..., description="Target X coordinate")
    y: int = Field(..., description="Target Y coordinate")
    duration: float = Field(0.2, description="Travel duration in seconds")
    window: Optional[str] = Field(None, description="Window title to focus first")


class HandsDragRequest(BaseModel):
    x: int = Field(..., description="Target X coordinate")
    y: int = Field(..., description="Target Y coordinate")
    duration: float = Field(0.5, description="Drag duration in seconds")
    button: str = Field("left", description="Mouse button to hold down")
    window: Optional[str] = Field(None, description="Window title to focus first")


class HandsScrollRequest(BaseModel):
    clicks: int = Field(..., description="Scroll amount (+ for UP, - for DOWN)")
    x: Optional[int] = Field(None, description="X coordinate to hover over before scrolling")
    y: Optional[int] = Field(None, description="Y coordinate to hover over before scrolling")
    smooth: bool = Field(True, description="Human-like micro-steps")
    horizontal: bool = Field(False, description="Scroll horizontally")
    window: Optional[str] = Field(None, description="Window title to focus first")


class HandsTypeRequest(BaseModel):
    text: str = Field(..., description="Text to type")
    wpm: Optional[float] = Field(None, description="Target Words Per Minute (e.g. 65)")
    profile: str = Field("natural", description="Typing profile ('natural', 'fast', 'careful', 'coder')")
    human_like: bool = Field(True, description="Simulate human variance and micro-pauses")
    introduce_typos: bool = Field(False, description="Simulate realistic typos and auto-correction")
    typo_rate: float = Field(0.015, description="Typo frequency per character")
    window: Optional[str] = Field(None, description="Window title to focus first")


class HandsKeyRequest(BaseModel):
    key: str = Field(..., description="Key name (e.g. 'enter', 'tab', 'esc', 'backspace', 'f5')")
    count: int = Field(1, description="Number of times to press")
    dwell: float = Field(0.05, description="Press dwell time in seconds")
    window: Optional[str] = Field(None, description="Window title to focus first")


class HandsHotkeyRequest(BaseModel):
    keys: str = Field(..., description="Key combination (e.g. 'ctrl+c', 'alt+tab', 'win+r')")
    window: Optional[str] = Field(None, description="Window title to focus first")


class HandsPasteRequest(BaseModel):
    text: str = Field(..., description="Text or code block to paste immediately via clipboard")
    window: Optional[str] = Field(None, description="Window title to focus first")


class HandsFocusRequest(BaseModel):
    title: str = Field(..., description="Window title substring to focus")


@hands_router.post("/click", summary="Perform click on physical desktop")
def hands_click(req: HandsClickRequest) -> Dict[str, Any]:
    return hands_mouse.click(
        x=req.x,
        y=req.y,
        button=req.button,
        clicks=req.clicks,
        interval=req.interval,
        duration=req.duration,
        window_title=req.window,
    )


@hands_router.post("/move", summary="Move physical cursor smoothly to (x, y)")
def hands_move(req: HandsMoveRequest) -> Dict[str, Any]:
    return hands_mouse.move_to(x=req.x, y=req.y, duration=req.duration, window_title=req.window)


@hands_router.post("/drag", summary="Drag cursor to (x, y) with button held down")
def hands_drag(req: HandsDragRequest) -> Dict[str, Any]:
    return hands_mouse.drag_to(x=req.x, y=req.y, duration=req.duration, button=req.button, window_title=req.window)


@hands_router.post("/scroll", summary="Scroll mouse wheel vertically or horizontally")
def hands_scroll(req: HandsScrollRequest) -> Dict[str, Any]:
    return hands_mouse.scroll(
        clicks=req.clicks,
        x=req.x,
        y=req.y,
        smooth=req.smooth,
        horizontal=req.horizontal,
        window_title=req.window,
    )


@hands_router.post("/type", summary="Type text with realistic human typing cadence")
def hands_type(req: HandsTypeRequest) -> Dict[str, Any]:
    engine = TypingEngine(profile=req.profile)
    stats = engine.type_text(
        text=req.text,
        wpm=req.wpm,
        human_like=req.human_like,
        introduce_typos=req.introduce_typos,
        typo_rate=req.typo_rate,
        window_title=req.window,
    )
    return {"status": "success", "stats": stats}


@hands_router.post("/key", summary="Press a single key or repeated key")
def hands_key(req: HandsKeyRequest) -> Dict[str, Any]:
    if req.window:
        focus_window(req.window)
    for _ in range(max(1, req.count)):
        hands_keyboard.press_single_key(req.key, dwell_time=req.dwell)
    return {"status": "success", "key": req.key, "count": req.count}


@hands_router.post("/hotkey", summary="Execute hotkey combination (e.g. 'ctrl+c')")
def hands_hotkey(req: HandsHotkeyRequest) -> Dict[str, Any]:
    if req.window:
        focus_window(req.window)
    hands_keyboard.execute_hotkey(req.keys)
    return {"status": "success", "hotkey": req.keys}


@hands_router.post("/paste", summary="Instantly paste text block via clipboard")
def hands_paste(req: HandsPasteRequest) -> Dict[str, Any]:
    if req.window:
        focus_window(req.window)
    hands_keyboard.fast_paste(req.text)
    return {"status": "success", "length": len(req.text)}


@hands_router.get("/windows", summary="List all open desktop application windows")
def hands_list_all_windows() -> Dict[str, Any]:
    windows = list_windows()
    return {"status": "success", "count": len(windows), "windows": windows}


@hands_router.post("/focus", summary="Bring a desktop application window to front")
def hands_focus_window(req: HandsFocusRequest) -> Dict[str, Any]:
    success = focus_window(req.title)
    active = get_active_window_title()
    return {"status": "success" if success else "failed", "matched": success, "active_window": active}


@hands_router.get("/status", summary="Get Hands system status & active window")
def hands_status() -> Dict[str, Any]:
    import pyautogui
    w, h = pyautogui.size()
    return {
        "status": "ready",
        "screen_resolution": f"{w}x{h}",
        "active_window": get_active_window_title(),
        "available_profiles": list(PROFILES.keys()),
    }


app.include_router(hands_router)


# ═════════════════════════════════════════════════════════════════════════════
# 3. CANVAS ROUTER (Desktop 2 - Parallel Isolated Chrome)
# ═════════════════════════════════════════════════════════════════════════════

canvas_router = APIRouter(prefix="/canvas", tags=["Canvas (Parallel Isolated Desktop 2)"])


class CanvasNavigateRequest(BaseModel):
    url: str = Field(..., description="Target web URL to navigate to")


class CanvasMoveRequest(BaseModel):
    x: int = Field(..., description="Canvas X pixel coordinate")
    y: int = Field(..., description="Canvas Y pixel coordinate")
    duration: float = Field(0.3, description="Cursor glide duration in seconds")


class CanvasClickRequest(BaseModel):
    x: int = Field(..., description="Canvas X coordinate to click")
    y: int = Field(..., description="Canvas Y coordinate to click")
    button: str = Field("left", description="'left', 'right', or 'middle'")


class CanvasTypeRequest(BaseModel):
    text: str = Field(..., description="Text to type into active canvas input")
    delay: float = Field(0.04, description="Delay between keystrokes in seconds")


class CanvasPressRequest(BaseModel):
    key: str = Field(..., description="Keyboard key to press inside canvas (e.g. 'Enter', 'Tab')")


class CanvasScrollRequest(BaseModel):
    delta_y: int = Field(..., description="Scroll delta in pixels (+ down, - up)")


class CanvasStatusHudRequest(BaseModel):
    message: str = Field(..., description="Status message to display in canvas floating HUD")


@canvas_router.get("/status", summary="Get parallel canvas status, URL, & AI cursor location")
async def canvas_status() -> Dict[str, Any]:
    c = await get_canvas()
    if not c.page:
        raise HTTPException(status_code=503, detail="Canvas page not initialized")
    return {
        "active": True,
        "url": c.page.url,
        "cursor": list(c.cursor_pos),
        "viewport": {"width": c.width, "height": c.height},
        "active_task": eyes._ACTIVE_TASK_SESSION.task_name if eyes._ACTIVE_TASK_SESSION else None,
    }


@canvas_router.post("/navigate", summary="Navigate canvas to a URL")
async def canvas_navigate(req: CanvasNavigateRequest) -> Dict[str, Any]:
    c = await get_canvas()
    await c.set_status(f"Navigating to {req.url}...")
    await c.navigate(req.url)
    await c.set_status(f"Page Loaded: {req.url}")
    return {"success": True, "url": req.url}


@canvas_router.post("/move", summary="Glide visual neon AI cursor to (x, y)")
async def canvas_move(req: CanvasMoveRequest) -> Dict[str, Any]:
    c = await get_canvas()
    await c.move_mouse(req.x, req.y, duration=req.duration)
    return {"success": True, "cursor": [req.x, req.y]}


@canvas_router.post("/click", summary="Click inside canvas with visual neon ripple animation")
async def canvas_click(req: CanvasClickRequest) -> Dict[str, Any]:
    c = await get_canvas()
    await c.click(req.x, req.y, button=req.button)
    return {"success": True, "clicked_at": [req.x, req.y], "button": req.button}


@canvas_router.post("/type", summary="Type text into active canvas element")
async def canvas_type(req: CanvasTypeRequest) -> Dict[str, Any]:
    c = await get_canvas()
    await c.type_text(req.text, delay=req.delay)
    return {"success": True, "typed": req.text}


@canvas_router.post("/press", summary="Press a key inside canvas")
async def canvas_press(req: CanvasPressRequest) -> Dict[str, Any]:
    c = await get_canvas()
    await c.press_key(req.key)
    return {"success": True, "pressed": req.key}


@canvas_router.post("/scroll", summary="Scroll canvas viewport")
async def canvas_scroll(req: CanvasScrollRequest) -> Dict[str, Any]:
    c = await get_canvas()
    await c.scroll(req.delta_y)
    return {"success": True, "delta_y": req.delta_y}


@canvas_router.post("/hud", summary="Update floating HUD text on canvas")
async def canvas_hud(req: CanvasStatusHudRequest) -> Dict[str, Any]:
    c = await get_canvas()
    await c.set_status(req.message)
    return {"success": True, "message": req.message}


@canvas_router.get("/capture", summary="Capture ephemeral screenshot strictly within canvas")
async def canvas_capture() -> Dict[str, Any]:
    c = await get_canvas()
    return await c.capture(save=True)


@canvas_router.get("/ocr", summary="Run OCR strictly on current canvas content")
async def canvas_ocr(detailed: bool = False) -> Dict[str, Any]:
    c = await get_canvas()
    return await c.transcribe(detailed=detailed)


app.include_router(canvas_router)


# Also preserve top-level routes for backwards-compatibility with canvas_client.py
app.add_api_route("/health", lambda: {"status": "ok", "service": "AI Master Server"}, methods=["GET"])
app.add_api_route("/status", canvas_status, methods=["GET"])
app.add_api_route("/navigate", canvas_navigate, methods=["POST"])
app.add_api_route("/move", canvas_move, methods=["POST"])
app.add_api_route("/click", canvas_click, methods=["POST"])
app.add_api_route("/type", canvas_type, methods=["POST"])
app.add_api_route("/press", canvas_press, methods=["POST"])
app.add_api_route("/scroll", canvas_scroll, methods=["POST"])
app.add_api_route("/status_hud", canvas_hud, methods=["POST"])
app.add_api_route("/capture", canvas_capture, methods=["GET"])
app.add_api_route("/ocr", canvas_ocr, methods=["GET"])


# ═════════════════════════════════════════════════════════════════════════════
# 4. NATIVE CANVAS ROUTER (PyQt6 canvas_desktop.py bounds & state)
# ═════════════════════════════════════════════════════════════════════════════

native_router = APIRouter(prefix="/native", tags=["Native Canvas (PyQt6 Window)"])


@native_router.get("/bounds", summary="Get native PyQt6 canvas screen coordinates")
def native_bounds() -> Dict[str, Any]:
    b = get_canvas_bounds()
    return {"active": b is not None, "bounds": list(b) if b else None}


@native_router.get("/status", summary="Get full native PyQt6 canvas state from disk")
def native_status() -> Dict[str, Any]:
    if os.path.exists(CANVAS_STATE_FILE):
        try:
            import json
            with open(CANVAS_STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    return {"active": False, "bounds": None}


app.include_router(native_router)


# ═════════════════════════════════════════════════════════════════════════════
# 5. HIGH-LEVEL AUTOMATED ACTIONS ROUTER
# ═════════════════════════════════════════════════════════════════════════════

actions_router = APIRouter(prefix="/actions", tags=["Automated Actions & Workflows"])


class LoginActionRequest(BaseModel):
    url: str = Field("https://www.instagram.com/accounts/login/", description="Login page URL")
    username: str = Field(..., description="Account username or email to enter")
    password: str = Field(..., description="Account password to enter")
    platform: str = Field("instagram", description="Platform identifier (e.g. 'instagram', 'generic')")
    username_selector: Optional[str] = Field(None, description="Optional custom CSS selector for username input")
    password_selector: Optional[str] = Field(None, description="Optional custom CSS selector for password input")
    submit_selector: Optional[str] = Field(None, description="Optional custom CSS selector for submit button")


class SearchActionRequest(BaseModel):
    query: str = Field(..., description="Search query string")
    engine_url: str = Field("https://www.google.com", description="Search engine URL")


@actions_router.post("/login", summary="Automate full web login flow inside parallel canvas")
async def action_login(req: LoginActionRequest) -> Dict[str, Any]:
    c = await get_canvas()
    task_name = f"login_{req.platform.lower()}"
    eyes.start_task(task_name)

    steps_log = []

    try:
        # Step 1: Navigate to login page
        await c.set_status(f"Step 1/5: Navigating to {req.url}...")
        steps_log.append(f"Navigating to {req.url}")
        await c.navigate(req.url)
        await asyncio.sleep(3.5)

        # Step 2: Handle cookie banners if present
        for cookie_sel in [
            "button:has-text('Allow all cookies')",
            "button:has-text('Allow essential and optional cookies')",
            "button:has-text('Accept All')",
            "button:has-text('Accept')",
            "button:has-text('Decline optional cookies')",
            "button:has-text('Not now')",
        ]:
            try:
                btn = c.page.locator(cookie_sel).first
                if await btn.is_visible(timeout=1000):
                    box = await btn.bounding_box()
                    if box:
                        await c.set_status("Dismissing cookie prompt...")
                        await c.click(int(box["x"] + box["width"] / 2), int(box["y"] + box["height"] / 2))
                        await asyncio.sleep(1.2)
                        steps_log.append("Dismissed cookie consent banner")
                        break
            except Exception:
                pass

        # Step 3: Locate and fill Username field
        await c.set_status("Step 2/5: Locating username input...")
        username_el = None
        user_selectors = (
            [req.username_selector] if req.username_selector else [
                'input[name="username"]',
                'input[autocomplete="username"]',
                'input[name="email"]',
                'input[type="email"]',
                'input[placeholder*="username" i]',
                'input[placeholder*="phone" i]',
                'input[type="text"]',
            ]
        )

        for sel in user_selectors:
            try:
                el = c.page.locator(sel).first
                if await el.is_visible(timeout=1500):
                    username_el = el
                    break
            except Exception:
                continue

        if not username_el:
            raise HTTPException(status_code=404, detail="Could not locate username input field on the page.")

        user_box = await username_el.bounding_box()
        if not user_box:
            raise HTTPException(status_code=500, detail="Failed to calculate username input coordinates.")

        ux = int(user_box["x"] + user_box["width"] / 2)
        uy = int(user_box["y"] + user_box["height"] / 2)

        await c.set_status(f"Step 2/5: Gliding AI cursor to username field ({ux}, {uy})...")
        await c.move_mouse(ux, uy, duration=0.35)
        await c.click(ux, uy)
        await asyncio.sleep(0.3)

        await c.set_status(f"Step 2/5: Typing username '{req.username}'...")
        await c.type_text(req.username, delay=0.06)
        steps_log.append(f"Typed username '{req.username}' at ({ux}, {uy})")
        await asyncio.sleep(0.5)

        # Step 4: Locate and fill Password field
        await c.set_status("Step 3/5: Locating password input...")
        pass_el = None
        pass_selectors = (
            [req.password_selector] if req.password_selector else [
                'input[name="password"]',
                'input[type="password"]',
                'input[autocomplete="current-password"]',
            ]
        )

        for sel in pass_selectors:
            try:
                el = c.page.locator(sel).first
                if await el.is_visible(timeout=1500):
                    pass_el = el
                    break
            except Exception:
                continue

        if not pass_el:
            raise HTTPException(status_code=404, detail="Could not locate password input field on the page.")

        pass_box = await pass_el.bounding_box()
        if not pass_box:
            raise HTTPException(status_code=500, detail="Failed to calculate password input coordinates.")

        px = int(pass_box["x"] + pass_box["width"] / 2)
        py = int(pass_box["y"] + pass_box["height"] / 2)

        await c.set_status(f"Step 3/5: Gliding AI cursor to password field ({px}, {py})...")
        await c.move_mouse(px, py, duration=0.35)
        await c.click(px, py)
        await asyncio.sleep(0.3)

        masked_pass = "*" * len(req.password)
        await c.set_status(f"Step 3/5: Typing password {masked_pass}...")
        await c.type_text(req.password, delay=0.06)
        steps_log.append(f"Typed password at ({px}, {py})")
        await asyncio.sleep(0.5)

        # Step 5: Locate and click Login / Submit Button
        await c.set_status("Step 4/5: Locating submit button...")
        btn_el = None
        btn_selectors = (
            [req.submit_selector] if req.submit_selector else [
                'button[type="submit"]',
                'button:has-text("Log in")',
                'button:has-text("Log In")',
                'button:has-text("Sign in")',
                'button:has-text("Sign In")',
                'form button',
            ]
        )

        for sel in btn_selectors:
            try:
                el = c.page.locator(sel).first
                if await el.is_visible(timeout=1500):
                    btn_el = el
                    break
            except Exception:
                continue

        if btn_el:
            btn_box = await btn_el.bounding_box()
            if btn_box:
                bx = int(btn_box["x"] + btn_box["width"] / 2)
                by = int(btn_box["y"] + btn_box["height"] / 2)
                await c.set_status(f"Step 4/5: Clicking submit button at ({bx}, {by})...")
                await c.click(bx, by)
                steps_log.append(f"Clicked submit button at ({bx}, {by})")
            else:
                await c.set_status("Step 4/5: Pressing Enter to submit...")
                await c.press_key("Enter")
                steps_log.append("Pressed Enter to submit credentials")
        else:
            await c.set_status("Step 4/5: Pressing Enter to submit...")
            await c.press_key("Enter")
            steps_log.append("Pressed Enter to submit credentials")

        # Step 6: Wait for response and verify result via OCR
        await c.set_status("Step 5/5: Awaiting login response & analyzing results via OCR...")
        await asyncio.sleep(4.0)

        ocr = await c.transcribe(detailed=False)
        ocr_text = ocr.get("text", "")
        steps_log.append("Captured ephemeral screenshot and ran OCR analysis")

        # End ephemeral task session and purge screenshots
        deleted_count = eyes.end_task()
        await c.set_status(f"Login Flow Completed — Purged {deleted_count} temporary screenshots")

        return {
            "success": True,
            "action": "login",
            "platform": req.platform,
            "target_url": req.url,
            "username_submitted": req.username,
            "steps_executed": steps_log,
            "ocr_response_snippet": ocr_text[:500] if ocr_text else "(No OCR text detected)",
            "purged_ephemeral_screenshots": deleted_count,
        }

    except Exception as e:
        eyes.end_task()
        await c.set_status(f"Login error: {str(e)[:60]}")
        raise HTTPException(status_code=500, detail=str(e))


@actions_router.post("/order_chocolate", summary="End-to-end chocolate order flow on Swiggy Instamart")
async def action_order_chocolate(item: str = "KitKat") -> Dict[str, Any]:
    c = await get_canvas()
    eyes.start_task("order_chocolate_flow")
    await c.set_status(f"Initiating Chocolate Order: {item}...")

    await c.navigate("https://www.swiggy.com/instamart")
    await asyncio.sleep(3.0)

    await c.set_status("Gliding AI cursor to search area...")
    await c.move_mouse(500, 160, duration=0.4)
    await c.click(500, 160)
    await asyncio.sleep(0.5)

    await c.set_status(f"Typing '{item}'...")
    await c.type_text(item, delay=0.06)
    await asyncio.sleep(0.5)

    await c.set_status("Submitting search...")
    await c.press_key("Enter")
    await asyncio.sleep(4.0)

    await c.set_status("Verifying search results via OCR...")
    await c.capture(save=True)
    ocr = await c.transcribe(detailed=False)

    await c.set_status(f"Browsing {item} results...")
    await c.scroll(350)
    await asyncio.sleep(2.0)

    deleted = eyes.end_task()
    await c.set_status(f"Search Complete: {item} displayed. Purged {deleted} temp screenshots.")

    return {
        "success": True,
        "item": item,
        "ocr_preview": ocr.get("text", "")[:300],
        "purged_screenshots": deleted,
    }


app.include_router(actions_router)


# ── Server Runner ─────────────────────────────────────────────────────────────

def run_server(port: int = SERVER_PORT):
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    run_server()
