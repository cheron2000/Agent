---
name: atomic-step-task-planner
description: >-
  Breaks down complex desktop automation and GUI interactions into sequential, atomic sub-tasks.
  Enforces mandatory per-step visual confirmation and OCR verification before advancing to the next step.
  Use when planning or executing multi-step desktop workflows, UI tasks, browser interactions, or complex automations.
---

# Atomic Step Task Planner

The **Atomic Step Task Planner** transforms high-level, complex GUI and desktop automation requests into an explicit, sequential execution plan composed of atomic sub-tasks. 

### Mandatory Core Rule: Verify Meaningful State Changes
**Never execute uncertain or consequential actions blindly.** Every step must define an expected success condition, but the verification method and frequency must fit the action.

- Batch deterministic, low-risk actions that share a known target (for example, fill a known search field and submit it) when no intermediate decision is needed.
- Re-observe after navigation, submission, unexpected dialogs/errors, failed actions, and consequential operations.
- Do not capture a screenshot and run full OCR after every character, keypress, or deterministic action when no decision depends on the intermediate state.
- Prefer lightweight checks first: active-window/title, focus, input value, URL, DOM/accessibility state, or an expected element/text assertion.
- Use screenshot + OCR/vision when the state is ambiguous, structural metadata is unavailable, or visual verification is actually required.
- Prefer condition-based waits; fixed delays are bounded fallbacks, not the default synchronization strategy.

---

## 1. The Planning Phase: Task Decomposition

When presented with any multi-step desktop automation task:
1. **Analyze the Final Objective**: Identify the desired end-state (e.g., "Logged into account and on the 2FA security code entry page").
2. **Decompose into Atomic Sub-Tasks**: Break the workflow down so that each step performs exactly **one physical interaction** (one click, one typing event, or one keypress sequence).
3. **Define Per-Step Contract**: Every step in the plan must define:
   - **Step Name / Intent**: Clear description of what is being done.
   - **Target Locator**: Exact coordinates `(x, y)` or UI text anchor.
   - **Action**: Mouse click, smooth move, typing, hotkey, or wait.
   - **Expected Post-Condition**: What visual evidence on screen proves this step succeeded.
   - **Verification Assertion**: Exact OCR keywords, window title, or element bounding box to test.
   - **Recovery / Fallback**: Action to take if post-condition fails (e.g., dismiss popup, re-click, adjust coordinates).

---

## 2. Step Specification Schema

Every step must adhere to this structured format:

```json
{
  "step_number": 1,
  "intent": "Launch Chrome from Windows search",
  "action": "type_and_enter",
  "parameters": {
    "target_coord": [396, 1048],
    "text": "chrome",
    "key": "enter"
  },
  "wait_seconds": 2.0,
  "verification": {
    "type": "ocr_contains_any",
    "expected": ["104", "Profile", "Who's using Chrome", "Google Chrome"],
    "window_focus": "Google Chrome"
  },
  "recovery": {
    "on_failure": "re-click search bar at (396, 1048) and re-type 'chrome'"
  }
}
```

---

## 3. The Execution & Verification Loop

For every step $S_i$ in the plan:

```
                  ┌───────────────────────────────┐
                  │ 1. Focus Target Window / App  │
                  └───────────────┬───────────────┘
                                  ▼
                  ┌───────────────────────────────┐
                  │ 2. Execute Atomic Action      │
                  │    (Move, Click, or Type)     │
                  └───────────────┬───────────────┘
                                  ▼
                  ┌───────────────────────────────┐
                  │ 3. Wait for condition (bounded)│
                  └───────────────┬───────────────┘
                                  ▼
                  ┌───────────────────────────────┐
                  │ 4. Verify expected state      │
                  │    DOM/value/window first     │
                  └───────────────┬───────────────┘
                                  ▼
                    /───────────────────────────\
                   <   Post-Condition Verified?  >
                    \───────────────────────────/
                        │                   │
                   YES  │                   │  NO
                        ▼                   ▼
           ┌────────────────────────┐  ┌─────────────────────────┐
           │ Mark S_i DONE (Save    │  │ Execute Step Recovery   │
           │ verification evidence) │  │ (Retry up to 2 times or │
           └────────────┬───────────┘  │ re-align coordinates)   │
                        ▼              └────────────┬────────────┘
           ┌────────────────────────┐               │
           │ Advance to Step S_{i+1}│ <─────────────┘ (if recovered)
           └────────────────────────┘
```

### Verification Types:
1. **Text Appearance (`ocr_contains`)**:
   - Verify that expected text label or field content is present (e.g., verifying `_sushila_avhad` appears in the username field).
2. **Text Disappearance**:
   - Verify that loading spinners or dialogs closed.
3. **URL / Window Title Change**:
   - Verify that the browser navigation completed (e.g., URL contains `/codeentry/` or `/recaptcha/`).
4. **Button State Transition**:
   - Verify that a button became active (color changed from disabled grey/navy to active bright blue) or changed label to a spinner.
5. **Element Bounds / Contour Detection**:
   - Verify that a checkbox or modal dialog box was rendered at the expected bounding box.

---

## 4. Reusable Reference Implementation

Below is the standard, production-ready executor script pattern used by this skill:

```python
import time
import requests

DAEMON_URL = "http://127.0.0.1:8765"

class AtomicStepExecutor:
    def __init__(self, daemon_url=DAEMON_URL):
        self.daemon_url = daemon_url

    def focus(self, window_title: str):
        return requests.post(f"{self.daemon_url}/hands/focus", json={"window_title": window_title}).json()

    def click(self, x: int, y: int, clicks: int = 1, duration: float = 0.25):
        requests.post(f"{self.daemon_url}/hands/move", json={"x": x, "y": y, "duration": duration})
        time.sleep(0.05)
        return requests.post(f"{self.daemon_url}/hands/click", json={"x": x, "y": y, "clicks": clicks}).json()

    def type_text(self, text: str):
        return requests.post(f"{self.daemon_url}/hands/type", json={"text": text}).json()

    def press_key(self, key: str):
        return requests.post(f"{self.daemon_url}/hands/key", json={"key": key}).json()

    def execute_and_verify(self, step: dict, max_retries: int = 2) -> bool:
        """Executes a single atomic step and rigorously asserts its post-condition."""
        for attempt in range(max_retries + 1):
            print(f"Executing Step {step['step_number']}: {step['intent']} (Attempt {attempt + 1})")
            
            # 1. Focus window if specified
            if "window_focus" in step:
                self.focus(step["window_focus"])
                time.sleep(0.2)

            # 2. Execute Action
            act = step["action"]
            params = step.get("parameters", {})
            if act == "click":
                self.click(params["x"], params["y"], clicks=params.get("clicks", 1))
            elif act == "type":
                self.type_text(params["text"])
            elif act == "key":
                self.press_key(params["key"])
            elif act == "click_and_type":
                self.click(params["x"], params["y"])
                time.sleep(0.1)
                self.type_text(params["text"])

            # 3. Settle
            time.sleep(step.get("wait_seconds", 1.0))

            # 4. Capture & Verify
            cap = requests.post(f"{self.daemon_url}/eyes/capture", json={"save": True}).json()
            ocr = requests.post(f"{self.daemon_url}/eyes/ocr", json={"detailed": False}).json()
            ocr_text = ocr.get("text", "")

            # 5. Assert Post-Condition
            expected_keywords = step.get("verification", {}).get("expected", [])
            matched = any(k.lower() in ocr_text.lower() for k in expected_keywords)
            
            if matched:
                print(f"Step {step['step_number']} VERIFIED SUCCESS. Evidence: {cap.get('path')}")
                return True
            else:
                print(f"Step {step['step_number']} verification failed on attempt {attempt + 1}.")
                if attempt < max_retries and "recovery" in step:
                    print(f"Running recovery: {step['recovery']}")
                    time.sleep(1.0)

        return False
```

---

## 5. Summary of Best Practices

1. **Keep Decision Boundaries Explicit**: Combine deterministic actions only when they share a known target and no intermediate decision is required. For example, filling a known address bar and pressing Enter can be one action sequence, followed by navigation verification. Split actions when the next target depends on the preceding state.
2. **Dynamic Offset Awareness**: Recognize that error banners, dropdown menus, and responsive layouts can shift coordinates (e.g. login boxes shifting downwards by 65px when an error message appears). Always verify bounding boxes when coordinates change.
3. **Graceful Recovery**: When a step fails confirmation, do not blindly repeat the exact same broken input. Inspect the screenshot to see if a tooltip, passkey popup, or dialogue blocked the target, dismiss it with `Escape`, and re-attempt.
