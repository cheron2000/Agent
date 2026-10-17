# Windows Desktop Agent

[![CI](https://github.com/cheron2000/Agent/actions/workflows/ci.yml/badge.svg)](https://github.com/cheron2000/Agent/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A direct Windows desktop automation stack. The agent operates the actual visible Windows desktop using physical mouse, keyboard, OCR, and vision primitives. There is no canvas, desktop mirror, browser sandbox, or companion panel.

An agent operates the actual desktop you are using:

- **Eyes** captures the visible screen, performs OCR, finds visible text, and can describe screen content.
- **AgentHands** sends real Windows mouse and keyboard input through PyAutoGUI and Win32 helpers.
- **`ai_controller.py`** combines both into one Python interface for an agent.
- **`agent_server.py`** and **`api_client.py`** expose the same direct-desktop capabilities over an authenticated localhost REST API.

> [!TIP]
> **New AI Agent?** Read **[AGENTS.md](AGENTS.md)** first! It details the core **Observe → Reason → Act → Verify** loop, how to use `DesktopAgentController` without editing any code, and how to execute tasks using the Atomic Step Task Planner.

## Architecture

```text
Agent / task runner
        │
        ▼
DesktopAgentController (ai_controller.py)
   ┌────┴─────┐
   ▼          ▼
Eyes       AgentHands
capture,    mouse, keyboard,
OCR, find   focus, scroll
   └────┬─────┘
        ▼
Actual Windows desktop and active applications
```

## Setup

This project is Windows-oriented. Install dependencies in a virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -e .\Hands
```

Install the Tesseract OCR executable separately and ensure it is available on `PATH`. `Eyes/eyes.py` also checks common Windows Tesseract installation locations (`C:\Program Files\Tesseract-OCR\tesseract.exe`).

## Use from Python

### Grounded Element-by-ID (Recommended)

Eliminate coordinate guesswork by asking the vision pipeline to detect and number UI elements:

```python
from ai_controller import DesktopAgentController

desktop = DesktopAgentController()

with desktop.task("open_and_save"):
    # 1. Observe screen: captures UIA tree + tuned OCR + Set-of-Marks visual overlay
    obs = desktop.observe()
    print(f"Active window: {obs['active_window']}, found {len(obs['elements'])} elements")
    
    # 2. Click element directly by its numeric ID (hands resolves center coordinates)
    # Target can be chosen by LLM inspecting obs["elements"] or obs["image"]
    for el in obs["elements"]:
        if "Save" in el["name"]:
            desktop.click_element(el["id"])
            break
```

### Direct Coordinate & OCR Lookup

```python
from ai_controller import DesktopAgentController

desktop = DesktopAgentController()

with desktop.task("read_and_search"):
    print(desktop.windows())
    found = desktop.find("Search")
    if found.get("found"):
        desktop.click(found["x"], found["y"])
        desktop.type_text("desktop automation")
        desktop.press_key("enter")
```

## Authenticated Local REST API

To start the local agent server:

```powershell
python agent_server.py
```

The server listens on `http://127.0.0.1:8765/docs` and exposes `/eyes/*` and `/hands/*` routes.

### Security & Concurrency
- **Bearer Token Auth**: All operational endpoints require bearer token authentication. On startup, the server reads `AGENT_AUTH_TOKEN` from the environment or securely generates a 32-character token saved to `.agent_token` (ignored by git).
- **DNS Rebinding Protection**: Validates the `Host` header to reject cross-origin DNS rebinding attacks from browsers.
- **Input Concurrency Locking**: Physical keyboard and mouse endpoints are synchronized via a mutex lock to prevent interleaving from concurrent requests.
- **Clipboard Preservation**: `/hands/paste` automatically preserves and restores clipboard content.
- **Corner Fail-Safe**: PyAutoGUI corner emergency fail-safe is enabled. Moving the cursor to any screen corner immediately halts automation.

### API Client Usage

```python
from api_client import DesktopAgentClient

# Token is auto-discovered from AGENT_AUTH_TOKEN or .agent_token
client = DesktopAgentClient()

with client.task("automated_task"):
    # Element-by-ID observation
    obs = client.observe(annotate=True)
    if obs["elements"]:
        client.click_element(obs["elements"][0]["id"])
    
    # Direct input
    client.type_text("Hello desktop", profile="natural")
```

## Capabilities

| Need | Method | Description |
| --- | --- | --- |
| Grounded UI Observation | `observe(annotate=True)` | Hybrid UIA + tuned OCR + CV detection with Set-of-Marks visual badges |
| Situational Context Reasoning | `analyze_context(goal=...)` | Evaluates screen situation and produces explanatory utterance and action proposal |
| Autonomous Context Step | `step_with_context(goal=...)` | Performs full loop: observe -> assess situation -> state reasoning -> execute next action |
| Click UI Element by ID | `click_element(id)` | Resolves element ID from last observation to physical center coordinates |
| Zoom & Re-OCR Crop | `zoom(box_or_region, scale=3)` | High-resolution cropped observation for small buttons or blurry text |
| Wait for UI Text / State | `wait_for_text(text, timeout=10)` | Polling synchronization loop with screen change diffing |
| Inspect screen size & cursor | `screen_info()` | Screen width, height, and current mouse pointer coordinates |
| Capture desktop screenshot | `capture()` | Raw desktop screenshot saved to disk |
| OCR visible text | `transcribe(detailed=True)` | Full screen or cropped region text extraction via Tesseract |
| Find visible text | `find("Save")` | Find specific text box and center coordinates |
| Describe screen visually | `describe()` | Vision model / structured description of visible applications |
| List/focus applications | `windows()`, `focus("Notepad")` | Enumerate active windows and bring targeted window to foreground |
| Move/click physical mouse | `move()`, `click()` | Real mouse clicks with profile curves and modifiers |
| Scroll current app | `scroll()` | Send physical vertical/horizontal scroll events |
| Send keyboard input | `type_text()`, `paste_text()`, `press_key()` | Physical typing, clipboard paste, and hotkey chords |

## Screenshot Cleanup

Use `with desktop.task("name"):` (or `with client.task("name"):`) when a task captures screenshots. Eyes tracks task screenshots and automatically purges them when the context exits.

## Testing

Run the automated test suite with pytest:

```powershell
pytest -v
```

## License

This project is licensed under the [MIT License](LICENSE).
