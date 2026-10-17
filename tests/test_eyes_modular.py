"""Unit tests for Eyes modular architecture: coords, schema, annotate, diffing, observe, and uia."""

from unittest.mock import MagicMock, patch
import pytest
from PIL import Image

from Eyes.annotate import annotate_elements, draw_grid_map, format_spatial_layout_text
from Eyes.coords import box_area, box_center, box_iou, clamp_box
from Eyes.diffing import compute_frame_difference, has_screen_changed, wait_until
from Eyes.observe import deduplicate_and_merge_elements, sort_elements_reading_order
from Eyes.schema import Observation, UIElement, resolve_element, set_current_observation


# ── Coords & Geometry Tests ──────────────────────────────────────────────────
def test_coords_box_center():
    assert box_center([100, 200, 300, 400]) == (200, 300)
    assert box_center([0, 0, 10, 10]) == (5, 5)


def test_coords_clamp_box():
    assert clamp_box([-10, -5, 2500, 1500], 1920, 1080) == [0, 0, 1920, 1080]
    assert clamp_box([100, 200, 300, 400], 1920, 1080) == [100, 200, 300, 400]


def test_coords_box_area():
    assert box_area([10, 20, 60, 70]) == 2500
    assert box_area([50, 50, 50, 50]) == 0


def test_coords_box_iou():
    boxA = [0, 0, 10, 10]
    boxB = [0, 0, 10, 10]
    assert pytest.approx(box_iou(boxA, boxB), 0.01) == 1.0

    boxC = [5, 5, 15, 15]
    # Intersection is 5x5=25, Union is 100+100-25=175 -> IoU = 25/175 ~= 0.1428
    assert pytest.approx(box_iou(boxA, boxC), 0.01) == 0.143

    boxD = [20, 20, 30, 30]
    assert box_iou(boxA, boxD) == 0.0


# ── Schema & Observation Cache Tests ─────────────────────────────────────────
def test_schema_uielement_and_center():
    el = UIElement(id=1, role="Button", name="Submit", box=[10, 20, 50, 60])
    assert el.center == (30, 40)
    d = el.to_dict()
    assert d["id"] == 1
    assert d["role"] == "Button"
    assert d["name"] == "Submit"


def test_schema_observation_resolution():
    el1 = UIElement(id=1, role="Button", name="OK", box=[10, 10, 50, 30])
    el2 = UIElement(id=2, role="Edit", name="Input", box=[60, 10, 120, 30])
    obs = Observation(
        observation_id="obs_test_1",
        active_window="Notepad",
        elements=[el1, el2],
    )
    set_current_observation(obs)

    resolved = resolve_element(1)
    assert resolved is not None
    assert resolved.name == "OK"
    assert resolve_element(999) is None

    # Stale observation rejection
    assert resolve_element(1, observation_id="obs_stale_9") is None


# ── Annotate Tests ───────────────────────────────────────────────────────────
def test_annotate_elements():
    img = Image.new("RGB", (300, 200), (200, 200, 200))
    elements = [
        UIElement(id=1, role="Button", name="Save", box=[20, 20, 80, 50]),
        UIElement(id=2, role="Text", name="Title", box=[10, 10, 150, 30]),
    ]
    marked = annotate_elements(img, elements)
    assert marked.size == (300, 200)
    assert marked != img


def test_draw_grid_map():
    img = Image.new("RGB", (640, 480), (100, 100, 100))
    grid = draw_grid_map(img, columns=4, rows=4)
    assert grid.size == (640, 480)


def test_format_spatial_layout_text():
    elements = [
        UIElement(id=1, role="Button", name="Close", box=[1800, 10, 1900, 40]),
        UIElement(id=2, role="Document", name="Editor", box=[100, 200, 1800, 800]),
        UIElement(id=3, role="Button", name="Start", box=[10, 1040, 50, 1070]),
    ]
    text = format_spatial_layout_text(elements, screen_size=(1920, 1080))
    assert "Title & Top Navigation" in text
    assert "Main Application Area" in text
    assert "Bottom / Taskbar Area" in text


# ── Diffing & Polling Tests ──────────────────────────────────────────────────
def test_diffing_frame_difference():
    img1 = Image.new("RGB", (100, 100), (255, 255, 255))
    img2 = Image.new("RGB", (100, 100), (255, 255, 255))
    img3 = Image.new("RGB", (100, 100), (0, 0, 0))

    assert compute_frame_difference(img1, img2) == 0.0
    assert has_screen_changed(img1, img2) is False
    assert has_screen_changed(img1, img3) is True


def test_diffing_wait_until():
    counter = 0
    def check():
        nonlocal counter
        counter += 1
        return counter >= 3

    assert wait_until(check, timeout_s=1.0, poll_interval_s=0.01) is True


# ── Observation Deduplication & Sorting Tests ────────────────────────────────
def test_deduplicate_and_merge_elements():
    # UIA element with generic name
    uia = [UIElement(id=0, role="Button", name="", box=[100, 100, 200, 140])]
    # OCR element with text overlapping the button
    ocr = [UIElement(id=0, role="Text", name="Submit Order", box=[105, 105, 195, 135])]
    cv = []

    merged = deduplicate_and_merge_elements(uia, ocr, cv, iou_threshold=0.3)
    assert len(merged) == 1
    assert merged[0].role == "Button"
    assert merged[0].name == "Submit Order"
    assert merged[0].source == "uia"


def test_sort_elements_reading_order():
    el1 = UIElement(id=0, role="Button", name="B", box=[200, 10, 250, 30])
    el2 = UIElement(id=0, role="Button", name="A", box=[50, 10, 100, 30])
    el3 = UIElement(id=0, role="Button", name="C", box=[50, 80, 100, 100])

    sorted_els = sort_elements_reading_order([el1, el2, el3], y_band_size=30)
    assert [e.name for e in sorted_els] == ["A", "B", "C"]
