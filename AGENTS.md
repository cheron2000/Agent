# AGENTS.md — Agent Operating & Integration Guide

> [!IMPORTANT]
> **MANDATORY FIRST READ FOR ALL AGENTS**  
> If you are an AI agent tasked with automating, controlling, or performing actions in this repository, **read this file first before executing tasks or writing scripts.**  
> **Do NOT edit core engine files** (`ai_controller.py`, `Eyes/*`, `Hands/*`, `agent_server.py`). The automation framework is already fully built and tested. Use the existing Python APIs or REST endpoints directly.

---

## 1. The Core Mental Model: The Agent Loop

Every automation task must adhere to the **Observe → Reason → Act → Verify** loop:

```text
┌──────────────────────────────────────────────────────────────┐
│ 1. OBSERVE                                                  │
│    Call desktop.observe(annotate=True)                      │
│    Receives structured list of UI elements with unique IDs  │
└──────────────────────────────┬───────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────┐
│ 2. REASON (By Element ID)                                    │
│    Locate target by semantic attributes (name, role)         │
│    CRITICAL: NEVER calculate or guess raw (x, y) coordinates!│
└──────────────────────────────┬───────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────┐
│ 3. ACT                                                       │
│    Call desktop.click_element(target_id) or type_text(...)   │
│    Hands resolves ID to physical coordinates automatically   │
└──────────────────────────────┬───────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────┐
│ 4. VERIFY                                                    │
│    Verify state change (window title, wait_for_text, diff)   │
│    Only advance to next step once post-condition is verified │
└──────────────────────────────────────────────────────────────┘
```

---

## 2. Architecture Overview: What to Use

You do not need to understand every internal file. The interface is organized into a clean facade:

| Component | File | How to Use It |
|---|---|---|
| **Primary Controller Facade** | `ai_controller.py` | Import `DesktopAgentController`. This is your main entry point for python tasks. |
| **Vision & Grounding Engine** | `Eyes/` | Accessed via `desktop.observe()`, `desktop.zoom()`, `desktop.wait_for_text()`, and `desktop.transcribe()`. |
| **Physical Hands Engine** | `Hands/agent_hands` | Accessed via `desktop.click_element()`, `desktop.move()`, `desktop.type_text()`, `desktop.press_key()`, `desktop.focus()`. |
| **Local REST Server** | `agent_server.py` | Local FastAPI service listening on `http://127.0.0.1:8765`. |
| **REST API Client** | `api_client.py` | Import `DesktopAgentClient` if you prefer interacting over HTTP with bearer authentication. |
| **Atomic Planner Skill** | `.agents/skills/atomic-step-task-planner/SKILL.md` | The methodology for planning multi-step desktop workflows. |

---

## 3. How the Planner Skill Works

The **Atomic Step Task Planner** (`.agents/skills/atomic-step-task-planner/SKILL.md`) guarantees reliability on dynamic GUIs:

1. **Atomic Decomposition**: Break multi-step user tasks into sequential, atomic sub-tasks (one click, one text entry, or one keypress sequence).
2. **Mandatory Post-Condition**: Every step must define what visual evidence proves it succeeded (e.g. window title updated, modal appeared, or specific text became visible).
3. **No Blind Actions**: Never chain unverified clicks or typing events together.
4. **Lightweight Verification First**: Check active window title or accessibility state before running full OCR or image diffs.
5. **Adaptive Waiting**: Use `desktop.wait_for_text("expected", timeout=5)` instead of arbitrary hardcoded `time.sleep()` calls.
6. **Step Recovery**: If verification fails, re-observe to check if a dialogue, popup, or passkey blocked the screen. Dismiss with `Escape` and retry.

---

## 4. Practical Code Recipes

### Recipe 1: Initializing Controller & Task Session
Always wrap multi-step operations in `with desktop.task("task_name"):`. Any temporary observation screenshots captured during the session are automatically deleted on exit.

```python
from ai_controller import DesktopAgentController

desktop = DesktopAgentController()

with desktop.task("login_flow"):
    # All screenshots captured inside this block are cleaned up automatically
    ...
```

### Recipe 2: Grounded Observe & Click-by-ID (Primary Workflow)
Never guess coordinates. Let the vision pipeline detect the elements and click by ID:

```python
from ai_controller import DesktopAgentController

desktop = DesktopAgentController()

with desktop.task("open_settings"):
    # 1. Observe screen (synthesizes UIA + OCR + CV contours)
    obs = desktop.observe(annotate=True)
    print(f"Active Window: {obs['active_window']}, Total Elements: {len(obs['elements'])}")

    # 2. Pick target element by semantic attributes
    target = None
    for el in obs["elements"]:
        if el["name"] == "Settings" or "Settings" in el["name"]:
            target = el
            break

    # 3. Act by ID: Hands resolves physical center coordinates automatically
    if target:
        desktop.click_element(target["id"])
```

### Recipe 3: Typing Text, Pasting, and Hotkeys
`DesktopAgentController` simulates natural, human-like typing velocity and key intervals:

```python
# Natural keyboard typing with human delays
desktop.type_text("Hello World", profile="natural")

# Fast typing for large inputs or code snippets
desktop.type_text("npm run dev", profile="fast")

# Clipboard paste (automatically preserves existing clipboard contents)
desktop.paste_text("secret_password_or_token")

# Single key press
desktop.press_key("enter")
desktop.press_key("esc")

# Key chords / hotkeys
desktop.hotkey("ctrl", "s")
desktop.hotkey("alt", "tab")
```

### Recipe 4: Reading Text, OCR, and Zooming
When you need to read content, copy messages, or inspect tiny buttons:

```python
# 1. Extract all visible text via OCR
ocr_report = desktop.transcribe(detailed=True)
print("Visible text on screen:", ocr_report["text"])

# 2. High-resolution zoom on small or blurry text (by element ID or bounding box)
zoom_result = desktop.zoom(element_id=14, scale=3.0)
print("Zoomed OCR text:", zoom_result["text"])

# 3. Polling synchronization loop: wait until specific text appears
res = desktop.wait_for_text("Dashboard Loaded", timeout_s=10.0)
if res["success"]:
    print("Dashboard is ready!")
```

### Recipe 5: Window Management
Inspect and bring specific application windows to the foreground:

```python
# List open windows and active foreground window
status = desktop.windows()
print("Foreground:", status["active_window"])
print("Open windows:", status["windows"])

# Focus target window before interacting
desktop.focus("Google Chrome")
```

### Recipe 6: Using the REST API via `DesktopAgentClient`
If running outside the main Python process or calling the server over localhost:

```python
from api_client import DesktopAgentClient

# Token is auto-discovered from .agent_token or AGENT_AUTH_TOKEN
client = DesktopAgentClient()

with client.task("remote_task"):
    obs = client.observe(annotate=True)
    if obs["elements"]:
        # Click element by ID
        client.click_element(obs["elements"][0]["id"])
    
    # Type text
    client.type_text("Search query")
    client.press_key("enter")
```

---

## 5. Critical Operating & Safety Rules

1. **PyAutoGUI Emergency Fail-Safe**: PyAutoGUI's corner fail-safe is active. Moving the physical mouse cursor into any screen corner (e.g. `(0, 0)`) immediately triggers `FailSafeException`. Never intentionally park or target corner coordinates.
2. **Process Privilege Boundary**: A non-elevated Python agent cannot send mouse/keyboard input to an elevated (Administrator) window. Always ensure target applications run at standard user privileges.
3. **High-DPI Awareness**: Windows Per-Monitor High-DPI awareness is automatically enabled (`coords.py`). All coordinates emitted by `Eyes` and accepted by `Hands` are physical screen coordinates matching Windows desktop space.
4. **Screenshot Storage**: Never store screenshots outside the designated ephemeral directories or leave raw images behind. Use `with desktop.task(...):` to ensure zero disk pollution.
5. **Interactive Desktop Requirement**: Automation primitives require an active interactive Windows desktop session (`WinSta0\Default`). They cannot execute inside disconnected headless RDP sessions without a desktop allocation.
