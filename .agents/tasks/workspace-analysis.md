# Workspace Analysis: f:\Shreyash DOC\shreyash\Agent

## Executive Summary

This is an **autonomous desktop AI agent** framework built in Python. The project gives any AI model (Claude, GPT-4o, Gemini, local Ollama LLaVA, etc.) the ability to **see, understand, and physically interact with a Windows desktop environment** — capturing the screen, reading text via OCR, finding UI elements, and driving mouse and keyboard. A dedicated PyQt6 browser window ("AI Desktop Canvas") acts as an isolated, bounded workspace, and all visual state is strictly confined to that canvas. The project is composed of four tightly integrated subsystems: **Eyes** (vision/perception), **Hands** (keyboard/mouse actuation), **canvas_desktop** (the isolated GUI workspace), and **ai_controller** (the orchestration bridge).

---

## 1. Project Purpose

The agent's goal is to let an LLM complete real desktop tasks — browsing the web, filling forms, clicking buttons, reading screen text, opening applications — with no human in the loop. It is designed to run on Windows with high-DPI awareness, ephemeral screenshot storage, and strict spatial bounding (all actions happen only inside the canvas viewport, not the host desktop at large).

---

## 2. Architecture Overview

```
┌──────────────────────────────────────────────────────────┐
│                   AI / LLM Client                         │
│  (Claude Desktop, Cursor, GPT-4o, Antigravity, etc.)     │
└────────────┬──────────────────────┬──────────────────────┘
             │ MCP stdio            │ REST HTTP (port 8421)
             ▼                      ▼
     Eyes/eyes_mcp.py       Eyes/eyes_server.py (FastAPI)
             │                      │
             └──────────┬───────────┘
                        │ Python SDK import
                        ▼
              ┌─────────────────────┐
              │   ai_controller.py  │  ← Orchestration bridge
              │  CanvasAIController │    (bounds + ephemeral lifecycle)
              └────┬───────────┬────┘
                   │           │
          ┌────────▼─┐    ┌────▼──────────────┐
          │  Eyes/   │    │  Hands/agent_hands │
          │  eyes.py │    │  engine / mouse /  │
          │ (vision) │    │  keyboard          │
          └────┬─────┘    └────────────────────┘
               │ reads canvas_state.json
          ┌────▼──────────────────┐
          │  canvas_desktop.py    │
          │  AIDesktopCanvas      │  ← PyQt6 window + Chromium engine
          │  (writes bounds live) │
          └───────────────────────┘
                        │
              canvas_state.json  (shared IPC)
```

---

## 3. Key Files and Their Roles

### `canvas_desktop.py`
- **Role**: The isolated GUI workspace. A `QMainWindow` (PyQt6) containing a full Chromium browser (`QWebEngineView`), a status HUD (badge, status label, viewport bounds display, ephemeral storage indicator), and a URL/navigation bar.
- **Key detail**: On every `moveEvent`, `resizeEvent`, and `showEvent`, the window writes its exact global screen coordinates into `canvas_state.json`. A background thread refreshes this every 1 second.
- **Startup**: `python canvas_desktop.py https://chatgpt.com` — accepts any URL as an argument.

### `ai_controller.py`
- **Role**: The central orchestrator. The `CanvasAIController` class reads `canvas_state.json` via `get_canvas_bounds()`, pushes those bounds into both `eyes.set_canvas_region()` and `hands_mouse.set_canvas_bounds()`, and exposes a context-manager (`task(name)`) that wraps a `TaskSession`. On exit, the session auto-deletes every screenshot taken during that task.
- **Key methods**: `capture()`, `transcribe()`, `find_on_canvas()`, `click()`, `double_click()`, `scroll()`, `type_text()`, `paste_text()`, `press_key()`, `focus()`.

### `canvas_state.json`
- **Role**: Shared inter-process state file (IPC between `canvas_desktop.py` and `ai_controller.py`/`eyes.py`). Contains `bounds: [x, y, width, height]`, `hwnd` (window handle), and a `timestamp`.
- **Live state**: At last run, the canvas was positioned at `(21, 133)` with size `1252×703` pixels (HWND `461172`).

### `Eyes/eyes.py`
- **Role**: The core perception engine. Single-file module (~850+ lines) providing:
  - `capture()` — multi-tiered screen grabber (PIL `ImageGrab` → Windows GDI BitBlt → PyAutoGUI fallback), stores PNGs in `Eyes/screenshots/`
  - `read_text()` — OCR via Tesseract, returning plain text or word-level bounding boxes + confidence
  - `screen_map()` — Excel-style spatial grid (e.g. "A1", "H4") mapping OCR words to grid cells
  - `find_on_screen()` — fuzzy text/label locator returning pixel-precise `(x, y)` centers
  - `describe()` — sends screenshot to a vision LLM (Ollama LLaVA first, then OpenAI GPT-4o, then OCR fallback)
  - `click()`, `type_text()`, `press_key()`, `scroll()`, `get_screen_info()` — direct PyAutoGUI interactions
  - `TaskSession` / `start_task()` / `end_task()` — ephemeral lifecycle management
- **Canvas bounding**: Module-level `_ACTIVE_CANVAS_REGION` restricts all operations to the canvas viewport when set.
- **Tesseract paths probed**: `C:\Program Files\Tesseract-OCR\tesseract.exe`, `C:\Program Files (x86)\...`, and `~\AppData\Local\Programs\Tesseract-OCR\tesseract.exe`.
- **Vision model**: Defaults to `llava:7b` via Ollama at `http://localhost:11434/api/generate` (configurable via `VISION_MODEL` and `OLLAMA_URL` env vars). Falls back to OpenAI `gpt-4o-mini` if `OPENAI_API_KEY` is set, then falls back to OCR-only.

### `Eyes/eyes_mcp.py`
- **Role**: MCP (Model Context Protocol) server exposing Eyes tools over stdio. Enables direct integration with Claude Desktop, Cursor, Continue, Antigravity, and any MCP-compliant host.
- **Exposed tools**: `screen_capture`, `screen_ocr`, `screen_map`, `screen_find`, `screen_describe`, `screen_click`, `screen_type`, `screen_press_key`, `screen_scroll`, `screen_get_info`, `enhance_vision_prompt`.
- **Prompt**: `eyes_master_prompt()` exposes the full cognitive system prompt as an MCP prompt resource.
- **Transport**: `stdio` (standard MCP).

### `Eyes/eyes_server.py`
- **Role**: FastAPI REST server on port `8421`. Every `eyes.py` function is exposed as a POST or GET endpoint. Includes CORS middleware (open to all origins), Pydantic request models, and interactive Swagger UI at `http://localhost:8421/docs`.
- **Endpoints**: `/api/capture`, `/api/ocr`, `/api/screen-map`, `/api/find`, `/api/click`, `/api/type`, `/api/press-key`, `/api/scroll`, `/api/describe`, `/api/enhance-prompt`, `/api/system-prompt`, `/api/health`, `/api/info`.

### `Eyes/prompt_enhancer.py`
- **Role**: Transforms vague user instructions into structured vision-grounded execution plans. Contains `MASTER_AI_EYES_SYSTEM_PROMPT` (the AI's cognitive system prompt with OBSERVE→ORIENT→DECIDE→ACT→VERIFY cycle) and the `PromptEnhancer` class. Also generates client-specific prompts for Claude and OpenAI.

### `Hands/` (package: `agent_hands`)
- **Role**: Physical keyboard and mouse actuation subsystem with a focus on **hyper-realistic human typing simulation**.
- **`engine.py`**: `TypingEngine` class — Gaussian-distributed inter-key intervals, punctuation micro-pauses, cognitive hesitation pauses, optional QWERTY-adjacency typo simulation with backspace self-correction.
- **`mouse.py`**: `click()`, `double_click()`, `right_click()`, `scroll()`, `move_to()` — all clamped to `_ACTIVE_CANVAS_BOUNDS` when set.
- **`keyboard.py`**: `fast_paste()` (clipboard paste), `press_single_key()`.
- **`windows.py`**: `focus_window()` — brings a named window to foreground.
- **`config.py`**: Typing profiles — `natural` (~65 WPM), `fast` (~105 WPM), `careful` (~38 WPM), `coder` (~72 WPM).
- **`server.py`**: MCP server for Hands tools (`hands_type_text`, `hands_click`, `hands_scroll`, etc.).
- **`typos.py`**: QWERTY adjacency matrix for realistic typo simulation.
- **Packaging**: Installed as an editable package (`pip install -e .`) with a `pyproject.toml`.

### `tools.json`
- **Role**: A tool registry listing 28 discrete desktop automation skills, each pointing to a script in `scripts/`. Tools include OS-level operations: `OPEN_APP`, `OPEN_BROWSER`, `SCREENSHOT`, `SYSTEM_INFO`, `SHUTDOWN`, `MUTE_VOLUME`, `SET_BRIGHTNESS`, and vision-grounded tools (`DESCRIBE_SCREEN`, `READ_SCREEN`, `FIND_ON_SCREEN`, `CLICK_ELEMENT`).

### `scripts/`
- **Role**: 24 standalone Python/PowerShell scripts implementing the tools registered in `tools.json`. Each script is independently executable and accepts CLI arguments (e.g. `--url`, `--target`, `--level`). Examples: `OPEN_APP.py`, `SCREENSHOT.py`, `DESCRIBE_SCREEN.py`, `CLICK_ELEMENT.py`, `SHUTDOWN.py`.

### `Eyes/skills/`
- **Role**: A bundled skills marketplace (appears to be an Anthropic/Claude plugin format — `.claude-plugin/marketplace.json`). Contains 19 skill packages: `academy-guide`, `algorithmic-art`, `brand-guidelines`, `canvas-design`, `claude-api`, `discernment-nudge`, `doc-coauthoring`, `docx`, `frontend-design`, `internal-comms`, `mcp-builder`, `pdf`, `pptx`, `skill-creator`, `slack-gif-creator`, `theme-factory`, `webapp-testing`, `web-artifacts-builder`, `xlsx`. Each skill has a `SKILL.md` and optional templates/scripts. These are capability packs that the AI agent can load on demand.

### `Eyes/tool_schemas.json`
- **Role**: Standard JSON tool-calling schemas for both OpenAI (function calling format) and Anthropic (tool use format). Provides plug-and-play integration for `screen_capture`, `screen_ocr`, `screen_find`, `screen_describe`, `screen_click`, `screen_type`, `screen_press_key`, `screen_scroll`, `enhance_vision_prompt`.

### Log/State Files
- **`canvas_state.json`**: Live IPC state (bounds, HWND, timestamp). Currently populated — the canvas was last active.
- **`canvas_debug.log`**: Empty (debug logging not currently active).
- **`err.log`**: Empty (no recent errors).
- **`requirements.txt`**: Lists: `flask`, `flask-cors`, `requests`, `psutil`, `pyautogui`, `pillow`, `pycaw`, `comtypes`, `screen-brightness-control`, `pyperclip`, `pywin32`. Note: PyQt6, FastAPI, uvicorn, pytesseract, opencv-python, mcp are NOT listed here — they are likely installed in the venv separately or declared in `Hands/pyproject.toml`.

---

## 4. Technology Stack

| Layer | Technology |
|---|---|
| GUI Window | PyQt6 + QWebEngineView (Chromium) |
| Vision/OCR | Tesseract OCR via pytesseract, PIL ImageGrab, Windows GDI BitBlt |
| Vision LLM | Ollama (LLaVA 7B default), OpenAI GPT-4o-mini, Anthropic Claude (via API) |
| Mouse/Keyboard | PyAutoGUI (with fail-safe), pywin32 |
| REST API | FastAPI + Uvicorn (port 8421) |
| MCP Server | `mcp` library (`MCPServer`, stdio transport) |
| Typing Sim | Custom Gaussian keystroke timing engine (agent_hands) |
| Packaging | pyproject.toml (Hands), pip venv |
| OS | Windows only (GDI, DPI awareness, winId(), pywin32) |
| Python | 3.14 (inferred from `cpython-314.pyc` cache files) |

---

## 5. Data Flow Between Components

### Task Execution Flow
```
1. User/LLM issues a task instruction
          ↓
2. ai_controller.CanvasAIController.task("name") context enters
          ↓
3. sync_canvas_bounds() reads canvas_state.json → sets Eyes region + Hands bounds
          ↓
4. eyes.start_task() creates TaskSession (screenshot tracking begins)
          ↓
5. AI calls controller methods (capture / transcribe / find / click / type)
     ↓                              ↓
  eyes.py captures screen      agent_hands executes mouse/keyboard
  within canvas bounds         within canvas bounds
          ↓
6. context exits → eyes.end_task() deletes all session screenshots
```

### MCP Integration Flow
```
LLM client (Claude Desktop, Cursor)
  → stdio → eyes_mcp.py MCPServer
  → calls eyes.py functions directly
  → returns JSON results to LLM
```

### REST Integration Flow
```
External agent / HTTP client
  → POST http://localhost:8421/api/*
  → eyes_server.py FastAPI endpoint
  → calls eyes.py functions
  → returns JSON response
```

### Canvas State IPC
```
canvas_desktop.py (PyQt6 window)
  → on move/resize/show + every 1s timer
  → writes canvas_state.json { bounds, hwnd, timestamp }
        ↓
ai_controller.py / eyes.py
  → reads canvas_state.json on every operation
  → all screen operations strictly inside those pixel bounds
```

---

## 6. Eyes/ Subdirectory Structure

```
Eyes/
├── eyes.py               ← Core vision + interaction engine (~850 lines)
├── eyes_mcp.py           ← MCP server (stdio) — 11 tools + 1 prompt
├── eyes_server.py        ← FastAPI REST server (port 8421) — 13 endpoints
├── prompt_enhancer.py    ← Task prompt structuring + master system prompt
├── tool_schemas.json     ← OpenAI + Anthropic JSON tool-calling schemas
├── README.md             ← Integration guide (MCP, REST, SDK, CLI)
├── PROMPTS.md            ← Prompt engineering reference
├── test_demo.py          ← Demo/test file
├── screenshots/          ← Ephemeral screenshot storage (auto-purged per task)
└── skills/               ← Claude plugin marketplace (19 skill packs)
    ├── .claude-plugin/
    │   └── marketplace.json
    ├── README.md
    ├── THIRD_PARTY_NOTICES.md
    └── skills/
        ├── academy-guide/
        ├── algorithmic-art/
        ├── canvas-design/
        ├── claude-api/
        ├── docx/ pptx/ pdf/ xlsx/   (document generation skills)
        ├── frontend-design/
        ├── mcp-builder/
        ├── webapp-testing/
        └── ... (19 total)
```

---

## 7. Hands/ Subdirectory and Skills

### Hands/
```
Hands/
├── pyproject.toml           ← Package definition (agent_hands, pip install -e .)
├── README.md                ← Integration guide (MCP, CLI, profiles)
├── agent_hands/
│   ├── __init__.py
│   ├── engine.py            ← TypingEngine (Gaussian cadence, typos)
│   ├── keyboard.py          ← fast_paste(), press_single_key()
│   ├── mouse.py             ← click, scroll, move_to — canvas-bounded
│   ├── windows.py           ← focus_window()
│   ├── config.py            ← Typing profiles (natural/fast/careful/coder)
│   ├── typos.py             ← QWERTY adjacency matrix
│   ├── server.py            ← MCP server for Hands tools
│   ├── cli.py               ← agent-hands CLI
│   └── visual_overlay.py   ← (likely debug visual feedback)
├── tests/                   ← pytest test suite
│   ├── test_engine.py
│   ├── test_mouse.py
│   ├── test_server.py
│   └── test_typos.py
└── skills/                  ← Same Claude plugin marketplace (copy/symlink)
```

### Eyes/skills/ skill packs
The 19 skill packs are pre-built capability modules for Claude:
- **Document skills**: `docx`, `pdf`, `pptx`, `xlsx` — generate/edit Office documents
- **Design skills**: `canvas-design`, `algorithmic-art`, `brand-guidelines`, `theme-factory`, `frontend-design`
- **Development skills**: `claude-api`, `mcp-builder`, `webapp-testing`, `web-artifacts-builder`
- **Communication skills**: `internal-comms`, `slack-gif-creator`, `doc-coauthoring`, `academy-guide`
- **Meta skills**: `skill-creator`, `discernment-nudge`

---

## 8. Configuration Files

| File | Purpose |
|---|---|
| `canvas_state.json` | Live canvas viewport IPC state |
| `tools.json` | Tool registry for 28 desktop automation scripts |
| `requirements.txt` | Python dependencies (partial — missing PyQt6, FastAPI, pytesseract) |
| `Hands/pyproject.toml` | `agent_hands` package definition + entry points |
| `Eyes/tool_schemas.json` | JSON tool schemas for OpenAI and Anthropic API integration |
| `Eyes/skills/.claude-plugin/marketplace.json` | Claude plugin marketplace manifest |
| `venv/` | Python virtual environment |

---

## 9. Summary: What This Project Does and How It's Used

This project is a **complete desktop AI agent runtime for Windows**. Here is how it is used:

**Mode 1 — Integrated agent (ai_controller + canvas_desktop)**
1. Launch `python canvas_desktop.py https://chatgpt.com` to open the isolated browser canvas.
2. In your agent code, instantiate `CanvasAIController()`.
3. Wrap tasks in `with controller.task("name") as task:` — all perception and interaction are spatially bounded and screenshots are auto-deleted at the end.

**Mode 2 — MCP server for Claude Desktop / Cursor**
1. Point your MCP client config at `Eyes/eyes_mcp.py` (stdio) or `Hands/agent_hands/server.py`.
2. The AI model gains `screen_capture`, `screen_ocr`, `screen_find`, `screen_click`, `hands_type_text`, etc. as native tools.

**Mode 3 — REST API for any agent**
1. Run `python Eyes/eyes_server.py` to start the FastAPI server on port 8421.
2. Any external agent, script, or service calls HTTP endpoints to perceive and act on the desktop.

**Mode 4 — Standalone CLI**
- `python Eyes/eyes.py capture` / `ocr` / `find "Search"` / `click --target Submit`
- `agent-hands type "Hello world" --wpm 65 --typos`

---

## 10. Issues and Recommendations

### Issues Found

1. **`requirements.txt` is incomplete**: PyQt6, FastAPI, uvicorn, pytesseract, opencv-python, numpy, and the `mcp` library are all imported in the code but not listed. A developer following only `requirements.txt` will face import errors.
   - **Recommendation**: Audit all imports across `canvas_desktop.py`, `eyes.py`, `eyes_server.py`, `eyes_mcp.py`, and consolidate into a complete `requirements.txt` or move to a `pyproject.toml` for the top-level package.

2. **`canvas_state.json` coupling**: The IPC between `canvas_desktop.py` and `ai_controller.py` uses a JSON file on disk. If the canvas is not running, `get_canvas_bounds()` returns `None` silently and all Eyes/Hands operations fall back to the full screen — this is a potential containment violation.
   - **Recommendation**: Add an explicit check in `ai_controller.sync_canvas_bounds()` and raise or warn loudly when the canvas is not running rather than silently degrading to full-screen mode.

3. **`eyes_mcp.py` uses `from mcp.server.mcpserver import MCPServer`**: The import path `mcp.server.mcpserver` is non-standard (the official `mcp` SDK uses `mcp.server`). This may break depending on the installed `mcp` version.
   - **Recommendation**: Verify the installed MCP SDK version and align the import path.

4. **CORS is fully open in `eyes_server.py`** (`allow_origins=["*"]`): This is fine for local-only use but is a risk if the server is accidentally exposed on a network interface.
   - **Recommendation**: Default the server to `127.0.0.1` only (which it already does in `start_server()`), and document that it must not be exposed on `0.0.0.0` without auth.

5. **No `START_OLLLAMA_SERVER` typo fix**: `tools.json` contains `"START_OLLLAMA_SERVER"` (three L's) — a minor naming inconsistency.
   - **Recommendation**: Rename the key to `START_OLLAMA_SERVER` for consistency.

6. **Skills directory duplicated**: The `Eyes/skills/` directory appears in both `Eyes/` and `Hands/` — likely a copy rather than a symlink. This will cause the two copies to drift out of sync.
   - **Recommendation**: Keep one canonical copy at the project root (`Agent/skills/`) and reference it from both, or use a git submodule.

7. **Python 3.14 pre-release**: The `__pycache__` bytecode shows `cpython-314`, meaning this runs on a pre-release Python version. PyQt6, numpy, and several other native extension packages may not have stable wheels for 3.14 yet.
   - **Recommendation**: Pin to Python 3.11 or 3.12 (the latest stable release) for maximum package compatibility.

8. **`canvas_debug.log` and `err.log` are empty**: These log files exist but contain nothing. The codebase uses `print()` for logging rather than Python's `logging` module.
   - **Recommendation**: Wire `ai_controller.py` and `canvas_desktop.py` to the `logging` module and configure handlers to write to these log files, enabling proper debugging.
