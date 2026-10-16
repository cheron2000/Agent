"""Local REST API for direct Windows desktop perception and input.

The server exposes only the real-desktop Eyes and AgentHands capabilities.
There is no canvas, browser automation, virtual desktop, or Playwright runtime.
"""

import os
import sys
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import uvicorn

ROOT = os.path.dirname(__file__)
sys.path.extend([os.path.join(ROOT, "Eyes"), os.path.join(ROOT, "Hands")])

import eyes
import agent_hands.keyboard as hands_keyboard
import agent_hands.mouse as hands_mouse
from agent_hands.engine import TypingEngine
from agent_hands.windows import focus_window, get_active_window_title, list_windows

SERVER_PORT = 8765

app = FastAPI(title="Windows Desktop Agent", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:8765", "http://localhost:8765"],
    allow_methods=["*"],
    allow_headers=["*"],
)


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
    button: str = "left"
    clicks: int = Field(default=1, ge=1, le=3)


class MoveRequest(BaseModel):
    x: int
    y: int
    duration: float = Field(default=0.2, ge=0, le=5)


class ScrollRequest(BaseModel):
    clicks: int = Field(ge=-100, le=100)
    x: Optional[int] = None
    y: Optional[int] = None


class TypeRequest(BaseModel):
    text: str
    profile: str = "natural"
    typos: bool = False


class KeyRequest(BaseModel):
    key: str = Field(min_length=1)


class HotkeyRequest(BaseModel):
    keys: List[str] = Field(min_length=1)


class PasteRequest(BaseModel):
    text: str


class FocusRequest(BaseModel):
    window_title: str = Field(min_length=1)


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok", "service": "Windows Desktop Agent"}


@app.get("/eyes/info")
def eyes_info() -> Dict[str, Any]:
    return eyes.get_screen_info()


@app.post("/eyes/capture")
def eyes_capture(req: CaptureRequest) -> Dict[str, Any]:
    return eyes.capture(save=req.save, include_base64=req.include_base64)


@app.post("/eyes/ocr")
def eyes_ocr(req: OCRRequest) -> Dict[str, Any]:
    return eyes.read_text(detailed=req.detailed)


@app.post("/eyes/map")
def eyes_map(req: ScreenMapRequest) -> Dict[str, Any]:
    return eyes.screen_map(
        columns=req.columns,
        rows=req.rows,
        min_confidence=req.min_confidence,
    )


@app.post("/eyes/find")
def eyes_find(req: FindRequest) -> Dict[str, Any]:
    return eyes.find_on_screen(req.target, min_confidence=req.min_confidence)


@app.post("/eyes/describe")
def eyes_describe(req: DescribeRequest) -> Dict[str, Any]:
    return eyes.describe(prompt=req.prompt)


@app.post("/eyes/task/start")
def start_task(req: TaskRequest) -> Dict[str, Any]:
    session = eyes.start_task(req.task_name)
    return {"success": True, "task_name": session.task_name}


@app.post("/eyes/task/end")
def end_task() -> Dict[str, Any]:
    return {"success": True, "deleted_screenshots": eyes.end_task()}


@app.get("/hands/status")
def hands_status() -> Dict[str, Any]:
    return {
        "active_window": get_active_window_title(),
        "windows": list_windows(),
    }


@app.post("/hands/focus")
def hands_focus(req: FocusRequest) -> Dict[str, Any]:
    focused = focus_window(req.window_title)
    return {"success": focused, "active_window": get_active_window_title()}


@app.post("/hands/move")
def hands_move(req: MoveRequest) -> Dict[str, Any]:
    return hands_mouse.move_to(req.x, req.y, duration=req.duration)


@app.post("/hands/click")
def hands_click(req: ClickRequest) -> Dict[str, Any]:
    return hands_mouse.click(x=req.x, y=req.y, button=req.button, clicks=req.clicks)


@app.post("/hands/scroll")
def hands_scroll(req: ScrollRequest) -> Dict[str, Any]:
    return hands_mouse.scroll(clicks=req.clicks, x=req.x, y=req.y, smooth=True)


@app.post("/hands/type")
def hands_type(req: TypeRequest) -> Dict[str, Any]:
    if req.profile not in {"natural", "fast", "careful", "coder"}:
        raise HTTPException(status_code=422, detail="Unknown typing profile")
    return TypingEngine(profile=req.profile).type_text(req.text, introduce_typos=req.typos)


@app.post("/hands/key")
def hands_key(req: KeyRequest) -> Dict[str, Any]:
    hands_keyboard.press_single_key(req.key)
    return {"success": True, "key": req.key}


@app.post("/hands/hotkey")
def hands_hotkey(req: HotkeyRequest) -> Dict[str, Any]:
    hands_keyboard.execute_hotkey(req.keys)
    return {"success": True, "keys": req.keys}


@app.post("/hands/paste")
def hands_paste(req: PasteRequest) -> Dict[str, Any]:
    hands_keyboard.fast_paste(req.text)
    return {"success": True, "characters": len(req.text)}


def run_server(port: int = SERVER_PORT) -> None:
    uvicorn.run(app, host="127.0.0.1", port=port)


if __name__ == "__main__":
    run_server()
