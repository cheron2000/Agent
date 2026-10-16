# Windows Desktop Agent

This project is a direct Windows desktop automation stack. It has no canvas, desktop mirror, browser sandbox, or companion panel.

An agent operates the actual desktop you are using:

- **Eyes** captures the visible screen, performs OCR, finds visible text, and can describe screen content.
- **AgentHands** sends real Windows mouse and keyboard input through PyAutoGUI and Win32 helpers.
- **`ai_controller.py`** combines both into one Python interface for an agent.
- **`agent_server.py`** and **`api_client.py`** optionally expose the same direct-desktop capabilities over localhost HTTP.

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

This project is Windows-oriented. Install the dependencies in a virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install pytesseract opencv-python numpy mcp
pip install -e .\Hands
```

Install the Tesseract OCR executable separately and ensure it is available on `PATH`. `Eyes/eyes.py` also checks common Windows Tesseract installation locations.

## Use from Python

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

## Optional local API

```powershell
python agent_server.py
```

The server listens on `http://127.0.0.1:8765/docs` and exposes only `/eyes/*` and `/hands/*` routes. It has no canvas or browser endpoints.

## Capabilities

| Need | Method |
| --- | --- |
| Inspect screen size and cursor | `screen_info()` |
| Capture the actual desktop | `capture()` |
| OCR visible text | `transcribe(detailed=True)` |
| Find visible text | `find("Save")` |
| Describe screen visually | `describe()` |
| List/focus applications | `windows()`, `focus("Notepad")` |
| Move/click the real mouse | `move()`, `click()` |
| Scroll current app | `scroll()` |
| Send keyboard input | `type_text()`, `paste_text()`, `press_key()` |

## Screenshot cleanup

Use `with desktop.task("name"):` when a task captures screenshots. Eyes tracks task screenshots and deletes them when the context exits. Captures made outside a task can remain in `Eyes/screenshots/`.

## Important behavior

This controller acts on the real desktop, not a copy:

- Mouse movement and clicks affect your actual Windows applications.
- Typing goes to the focused application.
- Moving the cursor to a screen corner triggers PyAutoGUI's emergency fail-safe.
- OCR and visual description only see what is currently visible to the process.

`Eyes/README.md` and `Hands/README.md` describe their REST, MCP, CLI, and library interfaces in more detail.
