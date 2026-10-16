# Eyes Improvement Plan

## Goal

Evolve Eyes from a screenshot-and-OCR utility into a reliable, privacy-conscious perception and action-verification layer. The target system should identify UI elements accurately, choose safe actions based on confidence, and confirm the intended outcome after every action.

## Current baseline

Eyes currently provides:

- Windows-aware screenshot capture, with optional screen-region restriction.
- Tesseract OCR with word-level boxes and confidence scores.
- Text lookup based on OCR output.
- A grid-based screen map.
- Optional visual description through Ollama and fallback providers.
- Direct desktop click, type, key-press, and scroll helpers.
- A task session that tracks and deletes screenshots created during an active task.
- Standalone Python, FastAPI, and MCP interfaces.

The primary weaknesses are OCR-only element grounding, simple text matching, coordinate-driven actions without verification, optional screenshot cleanup, and limited automated evaluation.

## Design principles

1. Prefer structured sources over pixels. Use DOM and accessibility data when controlling a browser; use OCR and visual inference only when structured data is unavailable.
2. Never treat a coordinate as an element identity. Generate stable element records and act through those records whenever possible.
3. Verify every consequential action. Capture and compare state after click, navigation, typing, scrolling, and form submission.
4. Make uncertainty explicit. Return confidence, candidates, reason codes, and the recommended next perception step.
5. Minimize retained sensitive data. Use memory where possible and make temporary storage scoped, unique, and automatically cleaned up.
6. Keep desktop automation guarded. Confirm the target window and active canvas bounds before sending OS-level input.

## Target model

```text
Capture sources
  ├── Browser DOM / accessibility tree (when available)
  ├── Screenshot
  ├── OCR word boxes
  └── Optional vision model
          │
          ▼
Normalized perception model
  ├── ScreenState
  ├── Element records (ID, role, label, box, source, confidence)
  └── Candidate matches
          │
          ▼
Decision and safe action
  ├── Confidence policy
  ├── Target/window validation
  └── Action executor
          │
          ▼
Post-action verification
  ├── URL / DOM changes
  ├── Screenshot differences
  ├── OCR state changes
  └── Expected-state assertion
```

## Phased roadmap

### Phase 0 — Establish a safe baseline

**Objective:** Preserve existing behavior while making storage and failures observable.

- [ ] Add a configuration object for screenshot directory, storage mode, OCR command, timeouts, and confidence thresholds.
- [ ] Replace timestamp-only filenames with UUIDs to avoid overwriting multiple captures in the same second.
- [ ] Use one directory per task: `screenshots/<task-id>/`.
- [ ] Ensure task cleanup runs in `finally` paths, including server route failures and cancelled tasks.
- [ ] Add a `save=False` / in-memory OCR path that avoids writing temporary PNGs when persistence is unnecessary.
- [ ] Return consistent error fields and machine-readable error codes from all public methods.
- [ ] Log task ID, source type, capture time, and cleanup result without logging sensitive OCR text by default.

**Acceptance criteria:** A task that fails midway leaves no registered screenshots; ten captures in one second yield ten unique artifacts; OCR can run with no persistent image file.

### Phase 1 — Normalize perception results

**Objective:** Give every caller one stable, source-agnostic representation of what Eyes can see.

- [ ] Introduce dataclasses/Pydantic models for `ScreenState`, `Element`, `BoundingBox`, `CandidateMatch`, and `PerceptionSource`.
- [ ] Add a `perceive()` API that runs the configured sources and returns a `ScreenState`.
- [ ] Assign each element a capture-scoped ID such as `ocr:12`, `dom:button:4`, or `vision:3`.
- [ ] Include source provenance, confidence, label/text, role, bounds, center point, and optional attributes.
- [ ] Keep current `capture`, `read_text`, `screen_map`, and `find_on_screen` APIs as compatibility wrappers.
- [ ] Group adjacent OCR words into lines and phrases before matching; retain original word-level data for precision.

**Acceptance criteria:** One perception call returns a documented schema that can represent OCR-only and browser-structured elements without special-case client logic.

### Phase 2 — Browser DOM and accessibility adapter

**Objective:** Eliminate avoidable OCR dependence in the Playwright canvas.

- [ ] Create a browser adapter used by `parallel_desktop_server.py` and `parallel_canvas.py`.
- [ ] Extract accessible name, ARIA role, visible text, enabled state, bounding box, tag name, input value, and CSS selector/locator hints.
- [ ] Prefer Playwright locators or accessibility-derived targets for click/type actions.
- [ ] Normalize browser coordinates to the same `BoundingBox` format used by OCR.
- [ ] Fall back to OCR only when the DOM cannot expose the target (canvas, image-only UI, cross-origin limitations, or inaccessible content).
- [ ] Mark targets as stale after navigation, resize, or a meaningful state change.

**Acceptance criteria:** Browser buttons and inputs can be found by role/name with a source of `dom` and acted on without an OCR coordinate lookup.

### Phase 3 — Better matching and grounding

**Objective:** Make text-target selection robust and explainable.

- [ ] Add phrase matching across grouped OCR words.
- [ ] Use a fuzzy-match library such as `rapidfuzz` for spelling variation and partial labels.
- [ ] Score candidates using exactness, fuzzy score, OCR confidence, role compatibility, visibility, enabled state, and recency.
- [ ] Support filters: `role`, `near`, `within`, `index`, `min_confidence`, and `source`.
- [ ] Return ranked candidates when a request is ambiguous instead of silently choosing a weak match.
- [ ] Add a policy that blocks an action below the configured confidence threshold unless the caller explicitly overrides it.

**Acceptance criteria:** `find("Save", role="button")` can differentiate a Save button from unrelated “saved” text and returns a score plus rationale.

### Phase 4 — Closed-loop action verification

**Objective:** Confirm that actions had the expected result.

- [ ] Implement `ActionResult` with attempted target, execution status, pre-state ID, post-state ID, and verification result.
- [ ] Capture lightweight pre/post perception snapshots around actions.
- [ ] Add verifier strategies:
  - [ ] Browser URL or page-title change.
  - [ ] DOM/ARIA target visible, hidden, enabled, disabled, or value changed.
  - [ ] OCR text appears or disappears.
  - [ ] Screenshot structural/image difference exceeds a threshold.
- [ ] Allow callers to supply an expected condition, for example `text_appears("Saved")` or `input_value("search", "tea")`.
- [ ] Add retry rules only for safe, idempotent actions; never blindly repeat destructive actions.
- [ ] Capture failure context for debugging within the task's privacy policy.

**Acceptance criteria:** A successful type action confirms the expected input value in a browser; a click returns `unverified` rather than `success` when no expected change is detected.

### Phase 5 — Native desktop safety hardening

**Objective:** Make the PyAutoGUI/native route safer when a browser adapter is unavailable.

- [ ] Add a canvas-state freshness timestamp and reject stale bounds.
- [ ] Verify the target window handle, title, process ID, and visible bounds before an action.
- [ ] Validate that a proposed point is inside both the canvas bounds and the current target window bounds.
- [ ] Add an explicit dry-run mode that returns the intended action and target evidence without sending input.
- [ ] Require a fresh perception snapshot before clicking a low-confidence native target.
- [ ] Add a safe-stop/cancel token checked between multi-step operations.

**Acceptance criteria:** Native actions fail closed if the canvas window is absent, stale, obscured, or no longer matches the recorded window identity.

### Phase 6 — Visual intelligence and page-state understanding

**Objective:** Use visual models selectively for cases OCR and DOM cannot explain.

- [ ] Add image-difference detection for loading transitions, dialogs, and scroll progress.
- [ ] Add optional visual element detection for icon-only controls, image buttons, charts, and canvas apps.
- [ ] Use a vision model only after DOM/OCR grounding fails or when the caller explicitly requires a visual description.
- [ ] Cache perception results for a short, configurable period and invalidate on page/input events.
- [ ] Return a compact structural summary: window/page, modal state, primary regions, inputs, primary actions, alerts, and blockers.

**Acceptance criteria:** Eyes can identify a blocking modal or meaningful page change even when no useful text is available.

### Phase 7 — Evaluation, observability, and release readiness

**Objective:** Measure reliability before widening automation scope.

- [ ] Create anonymized local fixtures representing forms, dialogs, menus, search pages, icon-only controls, and OCR-heavy pages.
- [ ] Add fixture tests for OCR grouping, candidate ranking, coordinate conversion, and confidence thresholds.
- [ ] Add mocked Playwright tests for DOM extraction and action verification.
- [ ] Add integration tests for task cleanup, FastAPI endpoints, screenshot uniqueness, and failure handling.
- [ ] Define metrics: find accuracy, top-1 target accuracy, false-click rate, verification success rate, capture latency, OCR latency, and cleanup success rate.
- [ ] Record aggregate metrics without storing screenshots or raw screen text unless explicitly enabled for debugging.
- [ ] Publish compatibility guarantees and deprecation dates for the existing Eyes functions.

**Acceptance criteria:** A repeatable test suite reports the core metrics and protects compatibility for existing REST, MCP, and Python consumers.

## Proposed API direction

```python
state = eyes.perceive(
    sources=["dom", "ocr"],
    region=canvas_bounds,
    persist="memory",
)

match = state.find(
    "Search",
    role="textbox",
    min_confidence=0.85,
)

result = eyes.act(
    action="click",
    target=match.element_id,
    verify={"type": "element_focused"},
)
```

The existing functions should remain available during migration:

```python
eyes.capture()
eyes.read_text(detailed=True)
eyes.find_on_screen("Search")
eyes.click(target="Search")
```

## Suggested work packages

| Package | Depends on | Outcome |
| --- | --- | --- |
| A. Storage and task lifecycle | None | Safe, unique, ephemeral capture management. |
| B. Perception data model | A | A normalized result schema and compatibility adapters. |
| C. Playwright adapter | B | DOM/accessibility-first browser perception and targeting. |
| D. Matching engine | B | Ranked, explainable, confidence-aware grounding. |
| E. Action verifier | B, C, D | Closed-loop control with expected-state checks. |
| F. Native safety layer | A, B | Stale-bound detection and validated OS-level actions. |
| G. Evaluation suite | A–F incrementally | Measurable quality and regression protection. |

## Dependencies to consider

- `rapidfuzz` for deterministic fuzzy text matching.
- Playwright accessibility/locator APIs for browser structure.
- `Pydantic` for public models and FastAPI response contracts.
- OpenCV/Pillow for visual diffs and image preprocessing.
- A perceptual-hash library only if benchmarked as better than simple image-diff thresholds.

Avoid making a cloud vision provider mandatory. The system must remain functional with DOM/OCR only and should require explicit configuration before sending screen content to an external model.

## Definition of done

Eyes is ready for broader task automation when it can:

- find browser elements through DOM/accessibility data before OCR;
- return ranked targets with meaningful confidence and provenance;
- block unsafe low-confidence actions by default;
- verify actions against an explicit or inferred expected state;
- clean task artifacts on success, error, and cancellation;
- protect native desktop operations with current window/bounds validation; and
- demonstrate its accuracy and cleanup guarantees through automated tests.
