"""Unified Observation Engine: merges UIA, OCR, and CV into structured Observations."""

import datetime
import logging
import os
import time
import uuid
from contextlib import contextmanager
from typing import Dict, List, Optional, Tuple
from PIL import Image

try:
    from .annotate import annotate_elements
    from .coords import box_iou, get_screen_size
    from .cv_detect import detect_visual_controls
    from .ocr import extract_ocr_elements
    from .schema import Observation, UIElement, set_current_observation
    from .uia import extract_uia_elements, get_foreground_hwnd
except (ImportError, ValueError):
    from Eyes.annotate import annotate_elements
    from Eyes.coords import box_iou, get_screen_size
    from Eyes.cv_detect import detect_visual_controls
    from Eyes.ocr import extract_ocr_elements
    from Eyes.schema import Observation, UIElement, set_current_observation
    from Eyes.uia import extract_uia_elements, get_foreground_hwnd


logger = logging.getLogger("eyes.observe")


class StepTimer:
    """High-precision execution timer to measure CPU/burst time for discrete pipeline steps."""

    def __init__(self):
        self._start = time.perf_counter()
        self.burst_times: Dict[str, float] = {}

    @contextmanager
    def measure(self, step_name: str):
        t0 = time.perf_counter()
        try:
            yield
        finally:
            self.burst_times[step_name] = round((time.perf_counter() - t0) * 1000.0, 2)

    @property
    def total_burst_ms(self) -> float:
        return round((time.perf_counter() - self._start) * 1000.0, 2)


def deduplicate_and_merge_elements(
    uia_elements: List[UIElement],
    ocr_elements: List[UIElement],
    cv_elements: List[UIElement],
    iou_threshold: float = 0.4,
    mode: str = "balanced",
) -> List[UIElement]:
    """Merge UIA, OCR, and CV elements, prioritizing UIA and deduplicating by IoU."""
    merged: List[UIElement] = []

    # 1. Start with all UIA elements
    for uia_el in uia_elements:
        merged.append(
            UIElement(
                id=0,
                role=uia_el.role,
                name=uia_el.name,
                box=list(uia_el.box),
                enabled=uia_el.enabled,
                source="uia",
                conf=uia_el.conf,
            )
        )

    # 2. Add OCR elements: if an OCR element matches a UIA element with high IoU, enrich name if needed;
    # otherwise add as a new Text element.
    for ocr_el in ocr_elements:
        best_match = None
        best_iou = 0.0

        for m in merged:
            iou = box_iou(ocr_el.box, m.box)
            if iou > best_iou:
                best_iou = iou
                best_match = m

        if best_match and best_iou >= iou_threshold:
            # If the matching UIA element has no name or generic name, use the OCR text
            raw_name = (best_match.name or "").strip().lower()
            if not raw_name or raw_name in {"button", "item", "edit", "pane", "group"}:
                best_match.name = ocr_el.name
        else:
            merged.append(
                UIElement(
                    id=0,
                    role="Text",
                    name=ocr_el.name,
                    box=list(ocr_el.box),
                    enabled=True,
                    source="ocr",
                    conf=ocr_el.conf,
                )
            )

    # 3. Add CV elements if mode is deep or element count is sparse
    allow_cv = (mode == "deep") or (len(merged) < 15)
    if allow_cv and cv_elements:
        for cv_el in cv_elements:
            overlaps = any(box_iou(cv_el.box, m.box) > 0.25 for m in merged)
            if not overlaps:
                merged.append(
                    UIElement(
                        id=0,
                        role="Control",
                        name="",
                        box=list(cv_el.box),
                        enabled=True,
                        source="cv",
                        conf=cv_el.conf,
                    )
                )

    return merged


def sort_elements_reading_order(elements: List[UIElement], y_band_size: int = 24) -> List[UIElement]:
    """Sort elements top-to-bottom in Y-bands, and left-to-right within each band."""
    def sort_key(el: UIElement):
        y_band = el.box[1] // y_band_size
        x = el.box[0]
        return y_band, x

    return sorted(elements, key=sort_key)


def build_observation(
    screen_image: Image.Image,
    active_window_title: str = "Active Desktop",
    save_annotated: bool = True,
    screenshots_dir: Optional[str] = None,
    max_elements: int = 100,
    mode: str = "balanced",
    offset: Tuple[int, int] = (0, 0),
) -> Observation:
    """Capture and synthesize UIA, OCR, and visual cues into an Observation.
    
    Modes:
    - 'fast': Screenshot + UIA only (bypasses OCR and CV for minimal latency).
    - 'balanced': Screenshot + UIA + OCR (CV fallback only if element count < 10).
    - 'deep': Comprehensive perception running UIA, full OCR, and full CV edge detection.
    """
    timer = StepTimer()
    timings: Dict[str, float] = {}
    screen_w, screen_h = get_screen_size()
    obs_id = f"obs_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"

    with timer.measure("hwnd"):
        hwnd = get_foreground_hwnd()
    
    # 1. UIA Extraction Step
    with timer.measure("uia"):
        uia_elements = extract_uia_elements(hwnd=hwnd, max_elements=max_elements)

    # 2. OCR Extraction Step (Skipped in 'fast' mode)
    ocr_elements: List[UIElement] = []
    with timer.measure("ocr"):
        if mode in {"balanced", "deep"}:
            ocr_elements = extract_ocr_elements(screen_image, use_cache=True, offset=offset)

    # 3. CV Control Detection Step (Only in 'deep' mode, or 'balanced' when UI elements are sparse)
    cv_elements: List[UIElement] = []
    with timer.measure("cv"):
        if mode == "deep" or (mode == "balanced" and (len(uia_elements) + len(ocr_elements)) < 10):
            cv_elements = detect_visual_controls(screen_image, max_elements=50)
            if offset != (0, 0):
                for cv_el in cv_elements:
                    cv_el.box = [
                        cv_el.box[0] + offset[0],
                        cv_el.box[1] + offset[1],
                        cv_el.box[2] + offset[0],
                        cv_el.box[3] + offset[1],
                    ]
                    cv_el.center = (cv_el.center[0] + offset[0], cv_el.center[1] + offset[1])

    # 4. Deduplicate and Merge Step
    with timer.measure("dedup"):
        merged = deduplicate_and_merge_elements(uia_elements, ocr_elements, cv_elements, mode=mode)

    # 5. Spatial Reading-Order Sort Step
    with timer.measure("sort"):
        sorted_elements = sort_elements_reading_order(merged)[:max_elements]

    # 6. Sequential Grounding ID Assignment Step
    with timer.measure("assign_ids"):
        for idx, el in enumerate(sorted_elements, start=1):
            el.id = idx

    raw_path = None
    annotated_path = None

    # 7. Screenshot Saving and Set-of-Marks Annotation Step
    if screenshots_dir and os.path.exists(screenshots_dir):
        with timer.measure("save_raw"):
            raw_path = os.path.join(screenshots_dir, f"{obs_id}.png")
            screen_image.save(raw_path)

        if save_annotated:
            with timer.measure("annotate"):
                annotated_img = annotate_elements(screen_image, sorted_elements)
            with timer.measure("save_annotated"):
                annotated_path = os.path.join(screenshots_dir, f"{obs_id}_marked.png")
                annotated_img.save(annotated_path)

    # Calculate burst times for each atomic step
    timings["uia_burst_ms"] = timer.burst_times.get("uia", 0.0)
    timings["uia_ms"] = timings["uia_burst_ms"]

    timings["ocr_burst_ms"] = timer.burst_times.get("ocr", 0.0)
    timings["ocr_ms"] = timings["ocr_burst_ms"]

    timings["cv_burst_ms"] = timer.burst_times.get("cv", 0.0)
    timings["cv_ms"] = timings["cv_burst_ms"]

    timings["dedup_burst_ms"] = timer.burst_times.get("dedup", 0.0)
    timings["sort_burst_ms"] = timer.burst_times.get("sort", 0.0)
    timings["assign_id_burst_ms"] = timer.burst_times.get("assign_ids", 0.0)
    merge_total = round(timings["dedup_burst_ms"] + timings["sort_burst_ms"] + timings["assign_id_burst_ms"], 2)
    timings["merge_burst_ms"] = merge_total
    timings["merge_ms"] = merge_total

    save_raw = timer.burst_times.get("save_raw", 0.0)
    annotate = timer.burst_times.get("annotate", 0.0)
    save_ann = timer.burst_times.get("save_annotated", 0.0)
    save_total = round(save_raw + annotate + save_ann, 2)
    timings["save_raw_burst_ms"] = save_raw
    timings["annotate_burst_ms"] = annotate
    timings["save_annotated_burst_ms"] = save_ann
    timings["save_burst_ms"] = save_total
    timings["save_ms"] = save_total

    timings["total_burst_ms"] = timer.total_burst_ms
    timings["total_ms"] = timer.total_burst_ms

    logger.debug(
        "Observation %s [%s] completed in %.1f ms burst time (UIA: %.1fms, OCR: %.1fms, CV: %.1fms, Dedup: %.1fms, Sort: %.1fms, Save: %.1fms)",
        obs_id,
        mode,
        timings["total_burst_ms"],
        timings["uia_burst_ms"],
        timings["ocr_burst_ms"],
        timings["cv_burst_ms"],
        timings["dedup_burst_ms"],
        timings["sort_burst_ms"],
        timings["save_burst_ms"],
    )

    obs = Observation(
        observation_id=obs_id,
        active_window=active_window_title,
        elements=sorted_elements,
        image_path=raw_path,
        annotated_image_path=annotated_path,
        screen_size=(screen_w, screen_h),
        mode=mode,
        timings=timings,
    )

    set_current_observation(obs)
    return obs
