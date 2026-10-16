# AI Parallel Desktop Canvas

A Windows-oriented prototype for running browser automation in a separate, visible Chrome workspace while leaving the user's physical mouse and keyboard available. The primary runnable path is a FastAPI service that drives a persistent Playwright Chrome context; its actions are exposed over a local HTTP API and through a small Python/CLI client.

The repository also includes two reusable desktop-automation packages:

- **Eyes**: screenshot capture, Tesseract OCR, text grounding, vision-provider fallback, and an MCP/REST interface.
- **AgentHands**: Windows mouse and keyboard automation, human-like typing, window focus helpers, and an MCP interface.

See [ARCHITECTURE.md](ARCHITECTURE.md) for the current execution paths, data flow, API contract, and known implementation constraints.

## What currently works

The main service starts a visible Chrome app window with a dedicated persistent profile at `ai_chrome_profile/`. Playwright sends mouse, keyboard, navigation, scroll, and screenshot commands directly to that browser page, so those commands do not use the physical Windows mouse or keyboard. A script is injected into each page to draw a cyan AI cursor, click ripples, and a status HUD.

The server binds only to `127.0.0.1:8765`. A client can query status, navigate, move/click, type, press keys, scroll, capture the page, run OCR, and start/end an ephemeral screenshot task. There is also a scripted `order_chocolate` demonstration that navigates to Swiggy Instamart and performs a coordinate-based search; it does **not** add an item, authenticate, or complete a purchase.

## Repository layout

```text
Agent/
├── parallel_desktop_server.py  # Primary FastAPI + async Playwright runtime
├── canvas_client.py            # HTTP client and command-line interface
├── parallel_canvas.py          # Sync Playwright runtime and injected visual overlay
├── desktop_home.html           # Local page shown when the service starts
├── ai_controller.py            # Bridges native canvas to Eyes + AgentHands
├── canvas_desktop.py           # Alternative native PyQt6 browser canvas
├── canvas_state.json           # Runtime viewport bounds written by PyQt canvas
├── Eyes/                       # Vision/OCR library, REST API and MCP server
├── Hands/                      # AgentHands package, tests and MCP server
├── ai_chrome_profile/          # Generated Chrome profile; not source code
├── canvas_user_dir/            # Generated browser profile/cache; not source code
├── requirements.txt            # Partial/root dependency list
└── tools.json                  # Registry for separate Windows system scripts
```

## Requirements

- Windows 10/11 (the native desktop-control components use Win32 APIs).
- Python 3.10+; the current environment contains Python 3.14 bytecode, but the AgentHands package declares Python 3.10+.
- Google Chrome installed in the standard location for the primary service (`C:\Program Files\Google\Chrome\Application\chrome.exe`).
- Playwright browser support and a usable Chromium/Chrome channel.
- Tesseract OCR installed and on `PATH`, or installed in one of the locations checked in `Eyes/eyes.py`, for OCR endpoints.
- Optional: Ollama with a vision model such as `llava:7b` for visual descriptions.

The root `requirements.txt` is incomplete for the primary canvas server. Install the project dependencies explicitly in a virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install fastapi uvicorn playwright pydantic pytesseract opencv-python numpy mcp PyQt6 PyQt6-WebEngine
playwright install chromium
pip install -e .\Hands
```

`PyQt6` and `PyQt6-WebEngine` are only required for the alternative native canvas route. `mcp` is required by the Eyes and AgentHands MCP servers. Install the Tesseract executable separately; `pytesseract` is only its Python wrapper.

## Run the primary parallel canvas

From the repository root:

```powershell
python parallel_desktop_server.py
```

On startup, the server creates a visible Chrome app window and initially loads `desktop_home.html`. It then serves the local API at `http://127.0.0.1:8765`.

In another terminal:

```powershell
python canvas_client.py status
python canvas_client.py navigate https://example.com
python canvas_client.py move 500 250
python canvas_client.py click 500 250
python canvas_client.py type "Hello from the canvas"
python canvas_client.py scroll 400
python canvas_client.py ocr
```

Coordinates for `move` and `click` are browser viewport coordinates, not desktop-screen coordinates. The browser window must be running for the client to work.

### Desktop Agent Control Center

The home canvas includes a local control panel for recording a task and selecting a browser-canvas permission mode:

- **Observe only** — console action requests are blocked.
- **Ask before actions** — each console action is placed in a visible approval queue.
- **Allow routine actions** — console action requests execute immediately in the browser canvas.

The panel is an initial control layer, not a natural-language Windows task runner. It controls only the Playwright browser canvas; it does not grant the page system-wide mouse, keyboard, file, or application access. The native `Eyes` and `AgentHands` path remains separate and needs additional window validation before it should be used as a desktop operator.

### Python client

```python
from canvas_client import CanvasClient

canvas = CanvasClient()
if canvas.is_alive():
    canvas.navigate("https://example.com")
    canvas.click(200, 150)
    canvas.type_text("Search text")
```

## Local HTTP API

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/health` | Service liveness check. |
| `GET` | `/status` | Current URL, cursor, viewport, and active task. |
| `POST` | `/navigate` | JSON: `{ "url": "https://..." }`. |
| `POST` | `/move` | JSON: `{ "x": 100, "y": 100, "duration": 0.3 }`. |
| `POST` | `/click` | JSON: `{ "x": 100, "y": 100, "button": "left" }`. |
| `POST` | `/type` | JSON: `{ "text": "...", "delay": 0.04 }`. |
| `POST` | `/press` | JSON: `{ "key": "Enter" }`. |
| `POST` | `/scroll` | JSON: `{ "delta_y": 300 }`. |
| `POST` | `/status_hud` | JSON: `{ "message": "..." }`. |
| `POST` | `/task/start` | JSON: `{ "task_name": "..." }`; begins screenshot tracking. |
| `POST` | `/task/end` | Deletes screenshots registered in the current task. |
| `GET` | `/capture` | Saves a browser-viewport PNG and returns its path. |
| `GET` | `/ocr` | OCRs a viewport screenshot; `?detailed=true` adds word boxes. |
| `POST` | `/order_chocolate?item=KitKat` | Runs the demo search flow only. |
| `GET` | `/agent/state` | Gets the console permission mode, task, pending action, and last result. |
| `POST` | `/agent/mode` | JSON: `{ "mode": "observe" | "ask" | "routine" }`. |
| `POST` | `/agent/task` | JSON: `{ "task": "..." }`; records the visible task. |
| `POST` | `/agent/actions/request` | Requests a browser action; queues or executes it according to permission mode. |
| `POST` | `/agent/actions/approve` | Executes the queued console action. |
| `POST` | `/agent/actions/reject` | Clears the queued console action. |

## Alternative native canvas

`canvas_desktop.py` provides a PyQt6 `QWebEngineView` window. It records the browser viewport's global screen bounds in `canvas_state.json`. `CanvasAIController` in `ai_controller.py` reads those bounds and configures Eyes and AgentHands to keep their capture and pointer operations inside the native canvas.

```powershell
python canvas_desktop.py https://chatgpt.com
```

This is a separate execution path from `parallel_desktop_server.py`; starting one does not start or control the other.

## Eyes and AgentHands

Eyes can be run as a separate REST service:

```powershell
python .\Eyes\eyes_server.py
```

It serves `http://127.0.0.1:8421` with capture, OCR, screen map, find, click, type, key press, scroll, describe, and prompt-enhancement endpoints. Its direct use is full-desktop capable unless a canvas region has been configured by the native controller.

Install and test AgentHands independently:

```powershell
pip install -e .\Hands
pytest .\Hands\tests
```

AgentHands can also start an MCP server with `agent-hands serve`. See the package-level READMEs in `Eyes/` and `Hands/` for their focused interfaces.

## Screenshot lifecycle and persistence

`Eyes.TaskSession` tracks images created while a task is active. `/task/start` or `CanvasAIController.task()` starts a session; `/task/end` or context-manager exit deletes registered image files. The page-capture and OCR endpoints register their screenshots only when such a session is active. Calling `/capture` or `/ocr` outside a task leaves the generated PNG in `Eyes/screenshots/`.

Chrome data is persistent by design in `ai_chrome_profile/`; it may retain site sessions, cookies, and cache. That directory and `canvas_user_dir/` are runtime data, not portable source assets.

## Testing and validation

The automated tests currently cover AgentHands typing, mouse utilities, MCP tool wrappers, and typo generation. They do not exercise the FastAPI canvas server, browser startup, browser isolation, OCR, or the native PyQt route.

```powershell
pytest .\Hands\tests
python -m py_compile ai_controller.py canvas_client.py canvas_desktop.py parallel_canvas.py parallel_desktop_server.py .\Eyes\eyes.py
```

## Important limitations

- The service's Playwright actions are isolated to Chrome, but the native `Eyes` and `AgentHands` route uses real screen capture, focus, and `pyautogui`; its containment depends on `canvas_state.json` being current.
- The current primary service does not validate coordinate bounds, URL schemes, or navigation destinations. It should be treated as a local development tool, not a security boundary.
- OCR requires an external Tesseract installation and may fail or misidentify dynamic or non-text UI.
- The injected HUD/cursor exists in web page DOM and can be removed or affected by page navigation or strict site policies; the service reinjects it after navigation on a best-effort basis.
- Browser launch uses a persistent profile. Do not use it with sensitive authenticated sessions without defining a profile and data-retention policy.
- `tools.json` references a `scripts/` directory that is not present in this workspace, so that registry is not currently executable here.

## Documentation

- [ARCHITECTURE.md](ARCHITECTURE.md) — current runtime topology, component responsibilities, flows, API, and risks.
- `Eyes/README.md` — Eyes usage and its REST/MCP interfaces.
- `Hands/README.md` — AgentHands command-line and MCP usage.
