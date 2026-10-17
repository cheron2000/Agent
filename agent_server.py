"""Local REST API for direct Windows desktop perception and input.

The server exposes direct-desktop Eyes and AgentHands capabilities with:
- Bearer token authentication and DNS rebinding (Host header) protection.
- Thread-safe concurrency control via physical input locking.
- Strict Pydantic model validation with Literal types and coordinate checks.
"""

import logging
import os
import secrets
import sys
import threading
from typing import Any, Dict, List, Literal, Optional

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field, model_validator
import uvicorn

ROOT = os.path.dirname(os.path.abspath(__file__))
if os.path.join(ROOT, "Eyes") not in sys.path:
    sys.path.insert(0, os.path.join(ROOT, "Eyes"))
if os.path.join(ROOT, "Hands") not in sys.path:
    sys.path.insert(0, os.path.join(ROOT, "Hands"))

try:
    import eyes
    import agent_hands.keyboard as hands_keyboard
    import agent_hands.mouse as hands_mouse
    from agent_hands.engine import TypingEngine
    from agent_hands.windows import focus_window, get_active_window_title, list_windows
except ImportError as err:
    # Fallback to direct path resolution
    sys.path.extend([os.path.join(ROOT, "Eyes"), os.path.join(ROOT, "Hands")])
    import eyes
    import agent_hands.keyboard as hands_keyboard
    import agent_hands.mouse as hands_mouse
    from agent_hands.engine import TypingEngine
    from agent_hands.windows import focus_window, get_active_window_title, list_windows

SERVER_PORT = 8765
logger = logging.getLogger("agent_server")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# ── Authentication & Security ────────────────────────────────────────────────
_active_token: Optional[str] = None
_token_lock = threading.Lock()


def get_current_token() -> str:
    """Retrieve or generate the single active authentication bearer token."""
    global _active_token
    with _token_lock:
        if _active_token:
            return _active_token

        env_token = os.environ.get("AGENT_AUTH_TOKEN")
        if env_token and env_token.strip():
            _active_token = env_token.strip()
            return _active_token

        token_file = os.path.join(ROOT, ".agent_token")
        if os.path.exists(token_file):
            try:
                with open(token_file, "r", encoding="utf-8") as f:
                    cached = f.read().strip()
                    if cached:
                        _active_token = cached
                        return _active_token
            except Exception as e:
                logger.warning("Could not read .agent_token file: %s", e)

        generated = secrets.token_urlsafe(32)
        try:
            with open(token_file, "w", encoding="utf-8") as f:
                f.write(generated)
        except Exception as e:
            logger.warning("Could not persist .agent_token file: %s", e)

        _active_token = generated
        return _active_token


security = HTTPBearer(auto_error=False)


def verify_auth(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> str:
    """Validate Bearer token or X-Agent-Token against server token."""
    token = None
    if credentials and credentials.credentials:
        token = credentials.credentials
    elif "x-agent-token" in request.headers:
        token = request.headers["x-agent-token"]

    expected = get_current_token()
    if not token or not secrets.compare_digest(token, expected):
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return token


# ── Concurrency Locks ────────────────────────────────────────────────────────
_hands_lock = threading.Lock()
_eyes_lock = threading.Lock()

# ── FastAPI App & Middleware ─────────────────────────────────────────────────
app = FastAPI(
    title="Windows Desktop Agent",
    description="Secure REST API for direct desktop automation via Eyes and AgentHands",
    version="1.1.0",
)

# DNS rebinding protection via Host header verification
@app.middleware("http")
async def validate_host_header(request: Request, call_next):
    raw_host = request.headers.get("host", "").split(":")[0].strip().lower()
    allowed_hosts = {"127.0.0.1", "localhost", "testserver"}
    extra_hosts = os.environ.get("ALLOWED_HOSTS", "")
    if extra_hosts:
        allowed_hosts.update(h.strip().lower() for h in extra_hosts.split(",") if h.strip())

    if raw_host not in allowed_hosts:
        return Response(
            content='{"detail": "Forbidden: Invalid Host header (DNS rebinding protection)"}',
            status_code=403,
            media_type="application/json",
        )
    return await call_next(request)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:8765", "http://localhost:8765"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Agent-Token"],
)


# ── Request / Response Models ────────────────────────────────────────────────
class CaptureRequest(BaseModel):
    save: bool = True
    include_base64: bool = False


class OCRRequest(BaseModel):
    detailed: bool = False


class ScreenMapRequest(BaseModel):
    columns: int = Field(default=12, ge=1, le=52)
    rows: int = Field(default=8, ge=1, le=100)
    min_confidence: int = Field(default=25, ge=0, le=100)


class FindRequest(BaseModel):
    target: str = Field(min_length=1)
    min_confidence: int = Field(default=30, ge=0, le=100)


class DescribeRequest(BaseModel):
    prompt: Optional[str] = None


class TaskRequest(BaseModel):
    task_name: str = Field(default="desktop_task", min_length=1)


class ClickRequest(BaseModel):
    x: Optional[int] = None
    y: Optional[int] = None
    button: Literal["left", "right", "middle"] = "left"
    clicks: int = Field(default=1, ge=1, le=3)

    @model_validator(mode="after")
    def validate_coordinates(self) -> "ClickRequest":
        if (self.x is None) ^ (self.y is None):
            raise ValueError("Both 'x' and 'y' must be provided together, or both omitted.")
        return self


class MoveRequest(BaseModel):
    x: int
    y: int
    duration: float = Field(default=0.2, ge=0, le=5)


class ScrollRequest(BaseModel):
    clicks: int = Field(ge=-100, le=100)
    x: Optional[int] = None
    y: Optional[int] = None

    @model_validator(mode="after")
    def validate_coordinates(self) -> "ScrollRequest":
        if (self.x is None) ^ (self.y is None):
            raise ValueError("Both 'x' and 'y' must be provided together, or both omitted.")
        return self


class TypeRequest(BaseModel):
    text: str
    profile: Literal["natural", "fast", "careful", "coder"] = "natural"
    typos: bool = False


class KeyRequest(BaseModel):
    key: str = Field(min_length=1)


class HotkeyRequest(BaseModel):
    keys: List[str] = Field(min_length=1)


class PasteRequest(BaseModel):
    text: str
    restore_clipboard: bool = True


class FocusRequest(BaseModel):
    window_title: str = Field(min_length=1)


# ── Routes: Health & Perception (Eyes) ───────────────────────────────────────
@app.get("/health")
def health() -> Dict[str, str]:
    """Public healthcheck endpoint for readiness probes."""
    return {"status": "ok", "service": "Windows Desktop Agent"}


@app.get("/eyes/info")
def eyes_info(_: str = Depends(verify_auth)) -> Dict[str, Any]:
    with _eyes_lock:
        return eyes.get_screen_info()


@app.post("/eyes/capture")
def eyes_capture(req: CaptureRequest, _: str = Depends(verify_auth)) -> Dict[str, Any]:
    with _eyes_lock:
        return eyes.capture(save=req.save, include_base64=req.include_base64)


@app.post("/eyes/ocr")
def eyes_ocr(req: OCRRequest, _: str = Depends(verify_auth)) -> Dict[str, Any]:
    with _eyes_lock:
        return eyes.read_text(detailed=req.detailed)


@app.post("/eyes/map")
def eyes_map(req: ScreenMapRequest, _: str = Depends(verify_auth)) -> Dict[str, Any]:
    with _eyes_lock:
        return eyes.screen_map(
            columns=req.columns,
            rows=req.rows,
            min_confidence=req.min_confidence,
        )


@app.post("/eyes/find")
def eyes_find(req: FindRequest, _: str = Depends(verify_auth)) -> Dict[str, Any]:
    with _eyes_lock:
        return eyes.find_on_screen(req.target, min_confidence=req.min_confidence)


@app.post("/eyes/describe")
def eyes_describe(req: DescribeRequest, _: str = Depends(verify_auth)) -> Dict[str, Any]:
    with _eyes_lock:
        return eyes.describe(prompt=req.prompt)


@app.post("/eyes/task/start")
def start_task(req: TaskRequest, _: str = Depends(verify_auth)) -> Dict[str, Any]:
    with _eyes_lock:
        session = eyes.start_task(req.task_name)
        return {
            "success": True,
            "task_name": session.task_name,
            "session_id": str(id(session)),
        }


@app.post("/eyes/task/end")
def end_task(_: str = Depends(verify_auth)) -> Dict[str, Any]:
    with _eyes_lock:
        deleted = eyes.end_task()
        return {"success": True, "deleted_screenshots": deleted}


# ── Routes: Physical Input (AgentHands) ──────────────────────────────────────
@app.get("/hands/status")
def hands_status(
    include_windows: bool = True,
    _: str = Depends(verify_auth),
) -> Dict[str, Any]:
    with _hands_lock:
        active = get_active_window_title()
        wins = list_windows() if include_windows else []
        return {
            "active_window": active,
            "window_count": len(list_windows()),
            "windows": wins,
        }


@app.post("/hands/focus")
def hands_focus(req: FocusRequest, _: str = Depends(verify_auth)) -> Dict[str, Any]:
    with _hands_lock:
        focused = focus_window(req.window_title)
        return {"success": focused, "active_window": get_active_window_title()}


@app.post("/hands/move")
def hands_move(req: MoveRequest, _: str = Depends(verify_auth)) -> Dict[str, Any]:
    with _hands_lock:
        return hands_mouse.move_to(req.x, req.y, duration=req.duration)


@app.post("/hands/click")
def hands_click(req: ClickRequest, _: str = Depends(verify_auth)) -> Dict[str, Any]:
    with _hands_lock:
        return hands_mouse.click(x=req.x, y=req.y, button=req.button, clicks=req.clicks)


@app.post("/hands/scroll")
def hands_scroll(req: ScrollRequest, _: str = Depends(verify_auth)) -> Dict[str, Any]:
    with _hands_lock:
        return hands_mouse.scroll(clicks=req.clicks, x=req.x, y=req.y, smooth=True)


@app.post("/hands/type")
def hands_type(req: TypeRequest, _: str = Depends(verify_auth)) -> Dict[str, Any]:
    with _hands_lock:
        return TypingEngine(profile=req.profile).type_text(req.text, introduce_typos=req.typos)


@app.post("/hands/key")
def hands_key(req: KeyRequest, _: str = Depends(verify_auth)) -> Dict[str, Any]:
    with _hands_lock:
        hands_keyboard.press_single_key(req.key)
        return {"success": True, "key": req.key}


@app.post("/hands/hotkey")
def hands_hotkey(req: HotkeyRequest, _: str = Depends(verify_auth)) -> Dict[str, Any]:
    with _hands_lock:
        hands_keyboard.execute_hotkey(req.keys)
        return {"success": True, "keys": req.keys}


@app.post("/hands/paste")
def hands_paste(req: PasteRequest, _: str = Depends(verify_auth)) -> Dict[str, Any]:
    with _hands_lock:
        hands_keyboard.fast_paste(req.text, restore_clipboard=req.restore_clipboard)
        return {
            "success": True,
            "characters": len(req.text),
            "clipboard_restored": req.restore_clipboard,
        }


def run_server(port: int = SERVER_PORT) -> None:
    token = get_current_token()
    logger.info("Starting Windows Desktop Agent on http://127.0.0.1:%d", port)
    logger.info("Bearer Token configured (check .agent_token or pass via AGENT_AUTH_TOKEN)")
    uvicorn.run(app, host="127.0.0.1", port=port)


if __name__ == "__main__":
    run_server()
