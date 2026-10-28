"""
Comprehensive regression tests for Eyes optimization features:
- Adaptive perception modes (fast, balanced, deep)
- OCR LRU cache hits, misses, and invalidation
- Coordinate offsets and bounding box preservation
- Stale observation ID isolation and bounded history
- Concurrent task session thread safety
- GDI and fallback resilience
- Compact LLM serialization
- Public API backwards compatibility
"""

import sys
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "Eyes") not in sys.path:
    sys.path.insert(0, str(ROOT / "Eyes"))

import eyes
from Eyes.coords import box_center, box_iou, get_screen_size
from Eyes.cv_detect import detect_visual_controls
from Eyes.ocr import (
    clear_ocr_cache,
    extract_ocr_elements,
    get_ocr_cache_stats,
    is_tesseract_available,
    preprocess_image_for_ocr,
)
from Eyes.observe import build_observation, deduplicate_and_merge_elements
from Eyes.schema import (
    Observation,
    UIElement,
    clear_observation_history,
    get_observation_by_id,
    resolve_element,
    set_current_observation,
)
from ai_controller import DesktopAgentController


# ── 1. OCR Caching & Invalidation Tests ──────────────────────────────────────
def test_ocr_caching_and_invalidation():
    clear_ocr_cache()
    img = Image.new("RGB", (200, 100), (240, 240, 240))

    # Mock pytesseract.get_tesseract_version and image_to_data
    fake_data = {
        "text": ["", "Hello", "World"],
        "conf": [0, 95, 90],
        "left": [0, 10, 80],
        "top": [0, 20, 20],
        "width": [0, 60, 70],
        "height": [0, 25, 25],
        "block_num": [0, 1, 1],
        "par_num": [0, 1, 1],
        "line_num": [0, 1, 1],
    }

    with patch("Eyes.ocr.is_tesseract_available", return_value=True), \
         patch("pytesseract.image_to_data", return_value=fake_data) as mock_ocr:

        # First call: should be a cache miss and call pytesseract
        elems1 = extract_ocr_elements(img, use_cache=True)
        assert len(elems1) == 1  # Grouped into "Hello World"
        assert elems1[0].name == "Hello World"
        assert mock_ocr.call_count == 1

        stats1 = get_ocr_cache_stats()
        assert stats1["hits"] == 0
        assert stats1["misses"] == 1
        assert stats1["size"] == 1

        # Second call on identical image: should hit cache and NOT call pytesseract
        elems2 = extract_ocr_elements(img, use_cache=True)
        assert len(elems2) == 1
        assert elems2[0].name == "Hello World"
        assert mock_ocr.call_count == 1  # Unchanged!

        stats2 = get_ocr_cache_stats()
        assert stats2["hits"] == 1
        assert stats2["hit_rate"] == 0.5

        # Invalidate cache
        clear_ocr_cache()
        stats3 = get_ocr_cache_stats()
        assert stats3["size"] == 0
        assert stats3["hits"] == 0

        # After invalidation: should miss cache and call pytesseract again
        elems3 = extract_ocr_elements(img, use_cache=True)
        assert mock_ocr.call_count == 2


def test_ocr_coordinate_offsets():
    clear_ocr_cache()
    img = Image.new("RGB", (100, 100), (255, 255, 255))
    fake_data = {
        "text": ["OK"],
        "conf": [90],
        "left": [20],
        "top": [30],
        "width": [40],
        "height": [20],
        "block_num": [1],
        "par_num": [1],
        "line_num": [1],
    }

    with patch("Eyes.ocr.is_tesseract_available", return_value=True), \
         patch("pytesseract.image_to_data", return_value=fake_data):

        # Offset (100, 200) with scale 2.0:
        # left = 20 / 2.0 + 100 = 110, top = 30 / 2.0 + 200 = 215
        elems = extract_ocr_elements(img, scale=2.0, offset=(100, 200), use_cache=False)
        assert len(elems) == 1
        box = elems[0].box
        assert box[0] == 110
        assert box[1] == 215


def test_ocr_missing_tesseract_graceful_fallback():
    clear_ocr_cache()
    img = Image.new("RGB", (50, 50), (200, 200, 200))
    with patch("Eyes.ocr.is_tesseract_available", return_value=False):
        elems = extract_ocr_elements(img)
        assert elems == []


# ── 2. Adaptive Observation Modes (fast, balanced, deep) ─────────────────────
def test_observation_adaptive_modes():
    img = Image.new("RGB", (640, 480), (128, 128, 128))

    fake_uia = [UIElement(id=0, role="Button", name="Close", box=[600, 10, 630, 30])]
    fake_ocr = [UIElement(id=0, role="Text", name="Settings", box=[50, 50, 120, 70])]
    fake_cv = [UIElement(id=0, role="Control", name="", box=[200, 200, 250, 250])]

    with patch("Eyes.observe.get_foreground_hwnd", return_value=12345), \
         patch("Eyes.observe.extract_uia_elements", return_value=fake_uia) as mock_uia, \
         patch("Eyes.observe.extract_ocr_elements", return_value=fake_ocr) as mock_ocr, \
         patch("Eyes.observe.detect_visual_controls", return_value=fake_cv) as mock_cv:

        # 1. Fast mode: runs UIA, skips OCR and CV completely
        obs_fast = build_observation(img, mode="fast", save_annotated=False)
        assert obs_fast.mode == "fast"
        assert len(obs_fast.elements) == 1
        assert obs_fast.elements[0].name == "Close"
        assert mock_ocr.call_count == 0
        assert mock_cv.call_count == 0
        assert "uia_ms" in obs_fast.timings
        assert "ocr_ms" in obs_fast.timings

        # 2. Balanced mode: runs UIA and OCR
        obs_balanced = build_observation(img, mode="balanced", save_annotated=False)
        assert obs_balanced.mode == "balanced"
        assert mock_ocr.call_count == 1
        assert len(obs_balanced.elements) >= 2

        # 3. Deep mode: runs UIA, OCR, and full CV edge detection
        obs_deep = build_observation(img, mode="deep", save_annotated=False)
        assert obs_deep.mode == "deep"
        assert mock_cv.call_count >= 1


# ── 3. Bounded Observation History & Stale ID Isolation ──────────────────────
def test_stale_observation_id_rejection():
    clear_observation_history()

    # Create Obs 1 with Element 1 = "Save"
    el1 = UIElement(id=1, role="Button", name="Save", box=[10, 10, 50, 30])
    obs1 = Observation(observation_id="obs_1001", active_window="App1", elements=[el1])
    set_current_observation(obs1)

    # Resolve from Obs 1
    res_obs1 = resolve_element(1, observation_id="obs_1001")
    assert res_obs1 is not None
    assert res_obs1.name == "Save"

    # Create Obs 2 with Element 1 = "Cancel" (screen state changed)
    el2 = UIElement(id=1, role="Button", name="Cancel", box=[10, 10, 50, 30])
    obs2 = Observation(observation_id="obs_1002", active_window="App2", elements=[el2])
    set_current_observation(obs2)

    # If caller asks for current element 1 -> gets "Cancel"
    res_curr = resolve_element(1)
    assert res_curr is not None
    assert res_curr.name == "Cancel"
    # If caller grounds against old obs_1001 -> gets "Save" from history
    res_old = resolve_element(1, observation_id="obs_1001")
    assert res_old is not None
    assert res_old.name == "Save"
    # If caller grounds against a non-existent or expired observation ID -> rejected as None
    assert resolve_element(1, observation_id="obs_expired_9999") is None


def test_bounded_observation_history_pruning():
    clear_observation_history()
    # Insert 15 observations (limit is 10)
    for i in range(15):
        obs = Observation(observation_id=f"obs_{i}", active_window=f"Win_{i}")
        set_current_observation(obs)

    # The oldest (obs_0 through obs_4) must have been pruned
    assert get_observation_by_id("obs_0") is None
    assert get_observation_by_id("obs_4") is None
    # The newest (obs_5 through obs_14) must remain available
    assert get_observation_by_id("obs_5") is not None
    assert get_observation_by_id("obs_14") is not None


# ── 4. Task Session Thread Safety & Concurrency ──────────────────────────────
def test_task_session_concurrency():
    session = eyes.start_task("concurrent_test")
    num_threads = 5
    items_per_thread = 20

    def worker(tid: int):
        for i in range(items_per_thread):
            session.add_screenshot(f"dummy_shot_{tid}_{i}.png")

    threads = [threading.Thread(target=worker, args=(t,)) for t in range(num_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(session.screenshots) == num_threads * items_per_thread
    eyes.end_task()


# ── 5. Compact Serialization for LLMs ────────────────────────────────────────
def test_observation_compact_serialization():
    el = UIElement(id=1, role="Button", name="Submit", box=[100, 200, 150, 230], conf=0.98)
    obs = Observation(
        observation_id="obs_comp",
        active_window="Browser",
        elements=[el],
        screen_size=(1920, 1080),
        mode="balanced",
        timings={"uia_ms": 12.5, "total_ms": 25.0},
    )

    full_dict = obs.to_dict(compact=False)
    compact_dict = obs.to_dict(compact=True)

    assert full_dict["observation_id"] == "obs_comp"
    assert "image_path" in full_dict

    # Compact representation removes heavy paths while keeping core grounding tokens
    assert compact_dict["observation_id"] == "obs_comp"
    assert "image_path" not in compact_dict
    assert compact_dict["element_count"] == 1
    assert compact_dict["elements"][0]["id"] == 1
    assert compact_dict["elements"][0]["name"] == "Submit"
    assert compact_dict["elements"][0]["center"] == [125, 215]
    assert compact_dict["mode"] == "balanced"
    assert "timings" in compact_dict


# ── 6. DesktopAgentController API Compatibility ──────────────────────────────
def test_desktop_controller_api_compatibility():
    controller = DesktopAgentController()

    fake_obs = {
        "success": True,
        "observation_id": "obs_ctrl_1",
        "elements": [{"id": 1, "name": "OK", "box": [10, 10, 30, 30], "center": [20, 20]}],
    }

    with patch("eyes.observe", return_value=fake_obs) as mock_obs, \
         patch("eyes.resolve_element_center", return_value=(20, 20)) as mock_resolve, \
         patch("ai_controller.click", return_value={"success": True}) as mock_click:

        # Test observe with mode and compact kwargs
        res = controller.observe(mode="fast", compact=True)
        assert res["success"] is True
        mock_obs.assert_called_with(save_annotated=True, max_elements=100, mode="fast", compact=True, save_raw=True)

        # Test click_element with observation_id
        click_res = controller.click_element(1, observation_id="obs_ctrl_1")
        assert click_res["success"] is True
        mock_resolve.assert_called_with(1, observation_id="obs_ctrl_1")
        mock_click.assert_called_with(x=20, y=20, button="left", clicks=1)


# ── 7. Additional Robustness & Regression Tests ──────────────────────────────
def test_ocr_autodiscovery_and_availability():
    """Verify that is_tesseract_available works and auto-discovers binary if present."""
    clear_ocr_cache()
    # Should run without error and return a boolean
    available = is_tesseract_available()
    assert isinstance(available, bool)


def test_ocr_cache_thread_safety():
    """Verify concurrent extract_ocr_elements calls under cache do not race."""
    clear_ocr_cache()
    img = Image.new("RGB", (100, 50), (255, 255, 255))
    fake_data = {
        "text": ["ThreadSafe"],
        "conf": [90],
        "left": [10],
        "top": [10],
        "width": [50],
        "height": [20],
        "block_num": [1],
        "par_num": [1],
        "line_num": [1],
    }

    with patch("Eyes.ocr.is_tesseract_available", return_value=True), \
         patch("pytesseract.image_to_data", return_value=fake_data):

        errors = []

        def worker():
            try:
                for _ in range(25):
                    elems = extract_ocr_elements(img, use_cache=True)
                    assert len(elems) == 1
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == [], f"Thread-safety errors encountered: {errors}"
        stats = get_ocr_cache_stats()
        assert stats["size"] == 1
        assert stats["hits"] > 0


def test_ocr_list_offset_support():
    """Verify offset passed as a list does not trigger TypeError: unhashable type: 'list'."""
    clear_ocr_cache()
    img = Image.new("RGB", (60, 30), (200, 200, 200))
    fake_data = {
        "text": ["Item"],
        "conf": [85],
        "left": [5],
        "top": [5],
        "width": [30],
        "height": [15],
        "block_num": [1],
        "par_num": [1],
        "line_num": [1],
    }

    with patch("Eyes.ocr.is_tesseract_available", return_value=True), \
         patch("pytesseract.image_to_data", return_value=fake_data):
        # Passing offset as list [50, 100]
        elems = extract_ocr_elements(img, offset=[50, 100], use_cache=True)
        assert len(elems) == 1
        assert elems[0].box[0] >= 50


def test_deep_mode_cv_retention_when_elements_exceed_15():
    """Verify that in mode='deep', CV elements are NOT arbitrarily dropped when merged >= 15."""
    img = Image.new("RGB", (640, 480), (128, 128, 128))
    # 20 UIA elements
    fake_uia = [
        UIElement(id=0, role="Button", name=f"Btn_{i}", box=[10, i * 20, 50, i * 20 + 15])
        for i in range(20)
    ]
    # CV element in a completely non-overlapping area
    fake_cv = [UIElement(id=0, role="Control", name="", box=[400, 400, 450, 450])]

    with patch("Eyes.observe.get_foreground_hwnd", return_value=12345), \
         patch("Eyes.observe.extract_uia_elements", return_value=fake_uia), \
         patch("Eyes.observe.extract_ocr_elements", return_value=[]), \
         patch("Eyes.observe.detect_visual_controls", return_value=fake_cv):

        obs = build_observation(img, mode="deep", save_annotated=False)
        cv_items = [e for e in obs.elements if e.source == "cv"]
        assert len(cv_items) == 1, "Deep mode must preserve CV elements even when element count >= 15"


def test_string_element_id_resolution():
    """Verify Observation.get_element and resolve_element handle string IDs like '1'."""
    el = UIElement(id=1, role="Button", name="Submit", box=[10, 10, 50, 30])
    obs = Observation(observation_id="obs_str_id", active_window="Test", elements=[el])
    set_current_observation(obs)

    el_obs = obs.get_element("1")
    assert el_obs is not None
    assert el_obs.name == "Submit"
    el_res = resolve_element("1")
    assert el_res is not None
    assert el_res.name == "Submit"


def test_step_timer_and_burst_times():
    """Verify StepTimer and individual step burst times are tracked in build_observation."""
    from Eyes.observe import StepTimer

    # Test StepTimer independently
    timer = StepTimer()
    with timer.measure("dummy_step"):
        time.sleep(0.01)

    assert "dummy_step" in timer.burst_times
    assert timer.burst_times["dummy_step"] >= 5.0
    assert timer.total_burst_ms >= 5.0

    # Test integration in build_observation
    img = Image.new("RGB", (320, 240), (200, 200, 200))
    obs = build_observation(img, mode="fast", save_annotated=False)

    required_burst_keys = [
        "uia_burst_ms",
        "ocr_burst_ms",
        "cv_burst_ms",
        "dedup_burst_ms",
        "sort_burst_ms",
        "assign_id_burst_ms",
        "merge_burst_ms",
        "total_burst_ms",
    ]
    for k in required_burst_keys:
        assert k in obs.timings, f"Missing burst timing key: {k}"
        assert isinstance(obs.timings[k], (int, float))


if __name__ == "__main__":
    sys.exit(pytest.main([__file__]))
