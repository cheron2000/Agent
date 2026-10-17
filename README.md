# Windows Desktop Agent

[![CI](https://github.com/cheron2000/Agent/actions/workflows/ci.yml/badge.svg)](https://github.com/cheron2000/Agent/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A direct Windows desktop automation stack. The agent operates the actual visible Windows desktop using physical mouse, keyboard, OCR, and vision primitives. There is no canvas, desktop mirror, browser sandbox, or companion panel.

An agent operates the actual desktop you are using:

- **Eyes** captures the visible screen, performs OCR, finds visible text, and can describe screen content.
- **AgentHands** sends real Windows mouse and keyboard input through PyAutoGUI and Win32 helpers.
- **`ai_controller.py`** combines both into one Python interface for an agent.
- **`agent_server.py`** and **`api_client.py`** expose the same direct-desktop capabilities over an authenticated localhost REST API.

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
    info = client.screen_info()
    client.click(500, 300)
    client.type_text("Hello desktop", profile="natural")
```

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

## Screenshot Cleanup

Use `with desktop.task("name"):` (or `with client.task("name"):`) when a task captures screenshots. Eyes tracks task screenshots and automatically purges them when the context exits.

## Testing

Run the automated test suite with pytest:

```powershell
pytest -v
```

## License

This project is licensed under the [MIT License](LICENSE).
