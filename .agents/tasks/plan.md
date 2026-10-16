# Implementation Plan — Windows Desktop AI Agent Bug Fixes

Workspace: `f:\Shreyash DOC\shreyash\Agent`  
Python interpreter: `venv\Scripts\python.exe`  
Test command (after pytest is installed): `venv\Scripts\python.exe -m pytest tests/ -v`  
Build check: `venv\Scripts\python.exe -c "import parallel_desktop_server"` (import-only smoke)

---

## Gap inventory → feature mapping

| Gap | Feature |
|-----|---------|
| 1 – Dependency drift | FEAT-001 |
| 2 – Input validation | FEAT-002 |
| 3 – Task lifecycle / screenshot cleanup | FEAT-002 |
| 4 – Stale canvas_state.json | FEAT-003 |
| 5 – tools.json missing scripts/ | FEAT-001 |
| 6 – Replace print() with logging | FEAT-003 |
| 7 – Overlapping canvas implementations | FEAT-001 |
| 8 – Smoke tests | FEAT-004 |
| 9 – Brittle order_chocolate demo | FEAT-002 |

---

- [ ] 1. **[FEAT-001 / Gap 1] Update `requirements.txt` with all missing dependencies.**  
      Add the following groups with inline comments (keep the existing entries):  
      `# core server`, `# OCR`, `# native canvas (optional)`, `# dev tools`.  
      Exact packages to add:  
      - core server: `fastapi==0.115.5`, `uvicorn[standard]==0.32.1`, `playwright==1.49.1`, `pydantic==2.10.3`, `httpx==0.28.1`  
      - OCR: `pytesseract==0.3.13`, `mcp==2.0.0`  
      - native canvas (optional): `PyQt6>=6.11.0` (already present — keep), `PyQt6-WebEngine>=6.11.0` (already present — keep)  
      - dev tools: `pytest==8.3.4`, `pytest-asyncio==0.24.0`  
      Rationale: fastapi, uvicorn, playwright, pydantic, and httpx are already importable in the venv confirming they are installed; declaring them in requirements.txt prevents future environment drift. pytest and pytest-asyncio are needed for FEAT-004.  
      Files: `requirements.txt`  
      Verify: `venv\Scripts\pip install -r requirements.txt --dry-run` — no error; `venv\Scripts\python.exe -m pytest --version` prints a version string.

- [ ] 2. **[FEAT-001 / Gap 5] Create `scripts/README.md` stub.**  
      Content must explain that the scripts referenced in `tools.json` (OPEN_VSCODE.ps1, MUTE_VOLUME.py, etc.) are not yet implemented and that `tools.json` is a declarative registry only. Do NOT modify `tools.json`.  
      Files: `scripts/README.md` (new)  
      Verify: `Test-Path scripts\README.md` returns `True`.

- [ ] 3. **[FEAT-001 / Gap 7] Mark `ParallelCanvasDesktop` as legacy in `parallel_canvas.py`.**  
      Add a prominent `LEGACY` docstring at the very top of the `ParallelCanvasDesktop` class body (before `__init__`) with the text:  
      `LEGACY: This class is the synchronous Playwright implementation and is NOT used by the primary server (parallel_desktop_server.py uses AsyncParallelDesktop directly). Retained for reference only. Do not instantiate from server code.`  
      Do NOT delete the class or change any other logic.  
      Files: `parallel_canvas.py`  
      Verify: `venv\Scripts\python.exe -c "from parallel_canvas import ParallelCanvasDesktop; print(ParallelCanvasDesktop.__doc__)"` — prints the LEGACY text.

- [ ] 4. **[FEAT-002 / Gap 2a] Add Pydantic coordinate validators to `MoveRequest` and `ClickRequest`.**  
      In `parallel_desktop_server.py`, import `field_validator` from pydantic (already imported as `from pydantic import BaseModel`; extend to `from pydantic import BaseModel, field_validator`).  
      Add a `@field_validator('x')` that clamps x to `[0, 1240]` and a `@field_validator('y')` that clamps y to `[0, 800]` on both `MoveRequest` and `ClickRequest`. Use `mode='before'` so the value is clamped, not rejected — coordinates outside range are silently clamped to the boundary.  
      Wait — re-read Gap 2: the spec says "clamp x to [0, 1240] and y to [0, 800]". For smoke test item (c) the spec says "POST /click rejects out-of-bounds coordinates (x=9999, y=9999) with 422". These conflict: clamping returns 200, rejection returns 422. Resolution: use `@field_validator` with `mode='after'` and **raise `ValueError`** if the value is outside range, which Pydantic converts to a 422 response. This satisfies the smoke test.  
      Files: `parallel_desktop_server.py`  
      Verify: `venv\Scripts\python.exe -m pytest tests/test_server_smoke.py::test_click_out_of_bounds -v` — test passes with 422.

- [ ] 5. **[FEAT-002 / Gap 2b] Add URL scheme validation to `/navigate`.**  
      In `parallel_desktop_server.py`, at the top of the `navigate()` endpoint handler (after the `canvas` None-check), parse `req.url` with `urllib.parse.urlparse` (stdlib, no new import needed beyond adding `from urllib.parse import urlparse`). If `parsed.scheme` is not in `{"http", "https"}`, raise `HTTPException(status_code=400, detail="Only http and https URLs are allowed")`.  
      Files: `parallel_desktop_server.py`  
      Verify: `venv\Scripts\python.exe -m pytest tests/test_server_smoke.py::test_navigate_rejects_non_http -v` — test passes with 400.

- [ ] 6. **[FEAT-002 / Gap 2c] Fix `set_status()` JavaScript string interpolation.**  
      In `parallel_desktop_server.py`, `AsyncParallelDesktop.set_status()` currently does:  
      ```python
      clean = status.replace("'", "\\'").replace('"', '\\"')
      await self.page.evaluate(f"window.__aiSetStatus('{clean}')")
      ```  
      Replace with `json.dumps()` for safe interpolation:  
      ```python
      import json  # add at top of file
      safe = json.dumps(status)          # produces a properly quoted JSON string
      await self.page.evaluate(f"window.__aiSetStatus({safe})")
      ```  
      Apply the same fix to `ParallelCanvasDesktop.set_status()` in `parallel_canvas.py`.  
      Files: `parallel_desktop_server.py`, `parallel_canvas.py`  
      Verify: `venv\Scripts\python.exe -c "import parallel_desktop_server"` — no import errors; manual review confirms `json.dumps` usage.

- [ ] 7. **[FEAT-002 / Gap 3] Wrap `/capture` and `/ocr` endpoints with `try/finally` and add `task_id` to `/task/start`.**  
      Sub-task A — `try/finally` in `/capture`:  
      The `capture_viewport` handler calls `canvas.capture(save=True)`. Wrap the body so that if an exception occurs, the path (if already written) is still registered with `eyes._ACTIVE_TASK_SESSION`. Because `AsyncParallelDesktop.capture()` already registers the path inside itself before returning, the `try/finally` wrapper at the endpoint level should ensure we call `eyes.end_task()` only if we started an implicit task — but per the architecture docs, capture is allowed outside a task. Correct approach: wrap `await canvas.capture(save=True)` in a `try/except Exception as e: raise HTTPException(status_code=500, detail=str(e))` so exceptions propagate as HTTP errors and the already-registered path stays in the session. Apply the same pattern to `/ocr`.  
      Sub-task B — `task_id` in `/task/start`:  
      Import `uuid` at the top of `parallel_desktop_server.py`. In `start_task()`, after `session = eyes.start_task(req.task_name)`, generate `task_id = str(uuid.uuid4())` and include it in the returned JSON: `{"success": True, "task_name": session.task_name, "task_id": task_id, "started_at": session.started_at}`.  
      Note: `TaskSession` in `eyes.py` does not have a `started_at` attribute — it only has `task_name`, `screenshots`, `is_active`. Add `self.started_at = time.time()` to `TaskSession.__init__` in `Eyes/eyes.py`.  
      Files: `parallel_desktop_server.py`, `Eyes/eyes.py`  
      Verify: `venv\Scripts\python.exe -m pytest tests/test_server_smoke.py::test_task_start_has_task_id -v` — test passes; returned JSON contains `task_id`.

- [ ] 8. **[FEAT-003 / Gap 4] Add staleness check and missing-file guard to `get_canvas_bounds()` and `sync_canvas_bounds()`.**  
      In `canvas_desktop.py`, rewrite `get_canvas_bounds()`:  
      1. If `CANVAS_STATE_FILE` does not exist → raise `RuntimeError("canvas_state.json not found; is canvas_desktop.py running?")`.  
      2. Load the JSON; if `"bounds"` key is absent → raise `RuntimeError("canvas_state.json is missing the 'bounds' key")`.  
      3. Check `data.get("timestamp")`; if `time.time() - timestamp > 5.0` → `logging.warning("canvas_state.json is stale (%.1fs old); canvas bounds may be inaccurate", age)`.  
      4. Return `tuple(b)` as before.  
      Add a module-level logger: `import logging; logger = logging.getLogger(__name__)`. Add a file handler writing to `canvas_debug.log` in the project root, and keep a console handler. Use `logger.info/warning/error` everywhere instead of `print()` throughout `canvas_desktop.py` (see Gap 6 below — both gaps are handled in this same file).  
      In `ai_controller.py`, `sync_canvas_bounds()` currently silently returns `None` if `get_canvas_bounds()` returns `None`. Since `get_canvas_bounds()` will now raise instead of returning `None`, update `sync_canvas_bounds()` to catch `RuntimeError` and log it with `logging.error(...)` rather than swallowing it.  
      Files: `canvas_desktop.py`, `ai_controller.py`  
      Verify: `venv\Scripts\python.exe -c "from canvas_desktop import get_canvas_bounds"` — no import errors.

- [ ] 9. **[FEAT-003 / Gap 6a] Replace `print()` with `logging` in `canvas_desktop.py`.**  
      This is the logging half of item 8 — do it in the same edit pass:  
      - Add at module level:  
        ```python
        import logging
        _log_formatter = logging.Formatter("%(asctime)s %(levelname)s [canvas_desktop] %(message)s")
        _file_handler = logging.FileHandler(os.path.join(os.path.dirname(__file__), "canvas_debug.log"), encoding="utf-8")
        _file_handler.setFormatter(_log_formatter)
        _console_handler = logging.StreamHandler()
        _console_handler.setFormatter(_log_formatter)
        logger = logging.getLogger(__name__)
        logger.setLevel(logging.DEBUG)
        logger.addHandler(_file_handler)
        logger.addHandler(_console_handler)
        ```  
      - Replace all `print(...)` calls with `logger.info(...)`, `logger.warning(...)`, or `logger.error(...)` as appropriate.  
      Files: `canvas_desktop.py`  
      Verify: `venv\Scripts\python.exe -c "from canvas_desktop import get_canvas_bounds"` — no import errors; running it creates `canvas_debug.log`.

- [ ] 10. **[FEAT-003 / Gap 6b] Replace `print()` with `logging` in `ai_controller.py`.**  
       Add at module level in `ai_controller.py`:  
       ```python
       import logging
       _log_formatter = logging.Formatter("%(asctime)s %(levelname)s [ai_controller] %(message)s")
       _file_handler = logging.FileHandler(os.path.join(os.path.dirname(__file__), "err.log"), encoding="utf-8")
       _file_handler.setFormatter(_log_formatter)
       _console_handler = logging.StreamHandler()
       _console_handler.setFormatter(_log_formatter)
       logger = logging.getLogger(__name__)
       logger.setLevel(logging.DEBUG)
       logger.addHandler(_file_handler)
       logger.addHandler(_console_handler)
       ```  
       Replace the two `print(f"\n[AI Controller]...")` calls inside `CanvasAIController.task()` with `logger.info(...)`. Replace the `print(...)` calls in `ensure_default_desktop()` in `canvas_desktop.py` that were missed in item 9 with `logger.info/warning`.  
       Files: `ai_controller.py`  
       Verify: `venv\Scripts\python.exe -c "from ai_controller import CanvasAIController"` — no import errors (note: this will fail at runtime on missing Hands/Eyes if not installed, but the import itself should not raise a logger-related error).

- [ ] 11. **[FEAT-002 / Gap 9] Harden the `/order_chocolate` endpoint.**  
       In `parallel_desktop_server.py`, make three changes to `execute_order_chocolate()`:  
       A — Add a prominent docstring warning at the very top of the function:  
       `"""WARNING: This endpoint uses hard-coded pixel coordinates and time delays tuned for Swiggy Instamart's layout as of 2024. Layout changes, login walls, geolocation prompts, or consent dialogs will break it. It does NOT complete a purchase. For production use, replace coordinate-based interaction with DOM selectors."""`  
       B — After Step 1 (navigate), add a URL check: after `await asyncio.sleep(3.0)`, read `canvas.page.url` and check `if "swiggy" not in canvas.page.url.lower()`. If the check fails, call `eyes.end_task()` and return a partial-progress JSON: `{"success": False, "reason": "Navigation did not reach swiggy.com", "step_reached": "navigate", "item": item}`.  
       C — Wrap each of the remaining numbered steps (Steps 2 through 8) in its own `try/except Exception as step_err` block. On exception, call `eyes.end_task()` (idempotent) and return: `{"success": False, "reason": str(step_err), "step_reached": "<step name>", "item": item, "ocr_preview": ""}`. The step names to use: "move_to_search", "click_search", "type_item", "press_enter", "capture_ocr", "scroll", "cleanup".  
       Files: `parallel_desktop_server.py`  
       Verify: `venv\Scripts\python.exe -c "import parallel_desktop_server"` — no import errors.

- [ ] 12. **[FEAT-004 / Gap 8] Create smoke test suite `tests/test_server_smoke.py`.**  
       Create `tests/__init__.py` (empty) so pytest can discover the package.  
       Create `tests/test_server_smoke.py` with the following structure:  
       - Import: `import pytest`, `from httpx import AsyncClient, ASGITransport`, `from unittest.mock import AsyncMock, MagicMock, patch`.  
       - Import the app: `import sys, os; sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))`. Then `from parallel_desktop_server import app`.  
       - Use a pytest fixture `async_client` that patches `parallel_desktop_server.canvas` with a `MagicMock` whose attributes simulate a live canvas (`.page` is not None, `.page.url` returns `"http://example.com"`, `.set_status` is an `AsyncMock`, `.navigate` is an `AsyncMock`, `.capture` is an `AsyncMock(return_value={"success": True, "path": "/tmp/x.png", "width": 1240, "height": 800, "error": None})`, `.transcribe` is an `AsyncMock(return_value={"success": True, "text": "", "elements": []})`).  
       - Also patch `parallel_desktop_server.eyes.start_task` and `parallel_desktop_server.eyes.end_task`.  
       - Mark all test functions with `@pytest.mark.asyncio`.  
       Tests to include:  
         a) `test_health_returns_200` — GET /health, assert status 200 and `resp.json()["status"] == "ok"`.  
         b) `test_navigate_rejects_non_http` — POST /navigate `{"url": "ftp://bad.example.com"}`, assert status 400.  
         c) `test_click_out_of_bounds` — POST /click `{"x": 9999, "y": 9999}`, assert status 422.  
         d) `test_task_start_has_task_id` — POST /task/start `{"task_name": "smoke"}`, assert status 200 and `"task_id"` in `resp.json()`.  
         e) `test_task_end_returns_deleted_count` — POST /task/end, assert status 200 and `"deleted_screenshots"` in `resp.json()`.  
       Use `ASGITransport(app=app)` with `AsyncClient` (httpx ≥ 0.20 pattern). Add `asyncio_mode = "auto"` in a `pytest.ini` or `pyproject.toml` section, or use `@pytest.mark.asyncio` decorator on each test.  
       Files: `tests/__init__.py` (new), `tests/test_server_smoke.py` (new)  
       Verify: `venv\Scripts\python.exe -m pytest tests/test_server_smoke.py -v` — all 5 tests pass.

- [ ] 13. **[Final] Run full test suite and confirm no regressions.**  
       Run `venv\Scripts\python.exe -m pytest tests/ -v`. All tests must pass. Also run `venv\Scripts\python.exe -m pytest Hands\tests\ -v` to confirm existing Hands tests are unaffected.  
       Files: none  
       Verify: zero failures across both test runs.

---

## Dependency order

Items 1 → 2 → 3 can be done in parallel (they touch separate files/sections).  
Item 4 depends on item 1 (pydantic validator syntax requires knowing pydantic v2 is declared).  
Item 5 depends on item 4 (both touch the navigate endpoint in the same file; do 4 first to avoid conflicts).  
Item 6 depends on items 4 and 5 (same file, `set_status` fix is independent but edit in same pass).  
Item 7 depends on item 6 (touching `parallel_desktop_server.py` and `Eyes/eyes.py`; do all server edits together).  
Items 8–10 can be done in parallel (separate files: `canvas_desktop.py`, `ai_controller.py`).  
Item 11 depends on items 4–7 (same server file; do last server edit).  
Item 12 depends on items 1, 4, 5, 7, 11 (tests verify those fixes).  
Item 13 depends on item 12.
