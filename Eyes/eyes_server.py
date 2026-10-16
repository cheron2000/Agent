"""
eyes_server.py  -  FastAPI REST Server for EYES
Allows ANY external AI agent, script, or framework to use EYES over HTTP REST endpoints.
Features interactive Swagger documentation at http://localhost:8421/docs.
"""

from typing import Optional, List
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

import eyes
from prompt_enhancer import PromptEnhancer, MASTER_AI_EYES_SYSTEM_PROMPT

app = FastAPI(
    title="EYES Vision Engine API",
    description="Universal visual perception and screen interaction API for ANY AI.",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request / Response Models ────────────────────────────────────────────────

class CaptureRequest(BaseModel):
    region: Optional[List[int]] = Field(None, description="[x, y, width, height] or null for full screen")
    save: bool = Field(True, description="Save screenshot file to disk")
    include_base64: bool = Field(False, description="Include base64 encoded image data")


class OCRRequest(BaseModel):
    region: Optional[List[int]] = Field(None, description="[x, y, width, height] or null")
    detailed: bool = Field(False, description="Return word bounding boxes and confidence")


class ScreenMapRequest(BaseModel):
    columns: int = Field(12, ge=1, le=52, description="Grid columns")
    rows: int = Field(8, ge=1, le=100, description="Grid rows")
    region: Optional[List[int]] = Field(None, description="[x, y, width, height] or null")
    min_confidence: int = Field(25, ge=0, le=100, description="Minimum OCR confidence")


class FindRequest(BaseModel):
    target: str = Field(..., description="Text or UI element label to search for")
    min_confidence: int = Field(30, description="Minimum OCR confidence score (0-100)")


class ClickRequest(BaseModel):
    x: Optional[int] = Field(None, description="X pixel coordinate")
    y: Optional[int] = Field(None, description="Y pixel coordinate")
    target: Optional[str] = Field(None, description="Text label to locate and click if (x, y) not provided")
    click_type: str = Field("left", description="'left', 'right', or 'double'")


class TypeRequest(BaseModel):
    text: str = Field(..., description="Text to type into active window")
    interval: float = Field(0.02, description="Delay between key presses in seconds")
    press_enter: bool = Field(False, description="Press Enter after typing")


class PressKeyRequest(BaseModel):
    key: str = Field(..., description="Key or shortcut combination like 'enter', 'tab', 'ctrl+c'")


class ScrollRequest(BaseModel):
    clicks: int = Field(-3, description="Clicks to scroll (-3 down, 3 up)")


class DescribeRequest(BaseModel):
    prompt: Optional[str] = Field(None, description="Custom prompt or question about screen")
    region: Optional[List[int]] = Field(None, description="[x, y, width, height] or null")


class EnhancePromptRequest(BaseModel):
    task: str = Field(..., description="Raw user prompt or task description")
    target_application: Optional[str] = Field(None, description="Name of the application or window")
    context_hints: Optional[List[str]] = Field(None, description="Visual hints or notes")
    safety_level: str = Field("standard", description="'standard' or 'strict'")


# ── Endpoints ────────────────────────────────────────────────────────────────

@app.get("/api/health")
def health():
    return {"status": "ok", "service": "EYES Vision Engine", "version": "1.0.0"}


@app.get("/api/info")
def get_info():
    """Get screen resolution, active bounds, and cursor position."""
    return eyes.get_screen_info()


@app.post("/api/capture")
def capture_screen(req: CaptureRequest):
    """Take a screenshot of the screen or region."""
    region = tuple(req.region) if req.region and len(req.region) == 4 else None
    return eyes.capture(region=region, save=req.save, include_base64=req.include_base64)


@app.post("/api/ocr")
def ocr_screen(req: OCRRequest):
    """Extract visible text from the screen using OCR."""
    region = tuple(req.region) if req.region and len(req.region) == 4 else None
    return eyes.read_text(region=region, detailed=req.detailed)


@app.post("/api/screen-map")
def map_screen(req: ScreenMapRequest):
    """Return a cell-based spatial transcription with precise OCR boxes."""
    region = tuple(req.region) if req.region and len(req.region) == 4 else None
    return eyes.screen_map(columns=req.columns, rows=req.rows, region=region, min_confidence=req.min_confidence)


@app.post("/api/find")
def find_element(req: FindRequest):
    """Find text or label coordinates on the screen."""
    return eyes.find_on_screen(target=req.target, min_confidence=req.min_confidence)


@app.post("/api/click")
def click_screen(req: ClickRequest):
    """Click at coordinates or find and click a text label."""
    return eyes.click(x=req.x, y=req.y, target=req.target, click_type=req.click_type)


@app.post("/api/type")
def type_into_screen(req: TypeRequest):
    """Type text into the currently focused window."""
    return eyes.type_text(text=req.text, interval=req.interval, press_enter=req.press_enter)


@app.post("/api/press-key")
def press_screen_key(req: PressKeyRequest):
    """Press a key or key combination."""
    if "+" in req.key:
        keys = [k.strip().lower() for k in req.key.split("+")]
        return eyes.press_key(keys)
    return eyes.press_key(req.key.strip().lower())


@app.post("/api/scroll")
def scroll_screen(req: ScrollRequest):
    """Scroll mouse wheel."""
    return eyes.scroll(clicks=req.clicks)


@app.post("/api/describe")
def describe_screen(req: DescribeRequest):
    """Visual description from multi-modal vision model."""
    region = tuple(req.region) if req.region and len(req.region) == 4 else None
    return eyes.describe(prompt=req.prompt, region=region)


@app.post("/api/enhance-prompt")
def enhance_prompt(req: EnhancePromptRequest):
    """Enhance any raw task prompt for high-precision vision interaction."""
    enhancer = PromptEnhancer()
    return enhancer.enhance_task_prompt(
        raw_task=req.task,
        target_application=req.target_application,
        context_hints=req.context_hints,
        safety_level=req.safety_level
    )


@app.get("/api/system-prompt")
def get_system_prompt():
    """Get the master system prompt for vision-grounded AI agents."""
    return {"system_prompt": MASTER_AI_EYES_SYSTEM_PROMPT}


def start_server(host: str = "127.0.0.1", port: int = 8421):
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    start_server()
