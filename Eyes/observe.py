"""Unified Observation Engine: merges UIA, OCR, and CV into structured Observations."""

import datetime
import logging
import os
import uuid
from typing import List, Optional, Tuple
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
    import time
    t_start = time.perf_counter()
    timings = {}
    screen_w, screen_h = get_screen_size()
    obs_id = f"obs_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"

    hwnd = get_foreground_hwnd()
    
    # 1. UIA Extraction
    t0 = time.perf_counter()
    uia_elements = extract_uia_elements(hwnd=hwnd, max_elements=max_elements)
    timings["uia_ms"] = round((time.perf_counter() - t0) * 1000.0, 2)

    # 2. OCR Extraction (Skipped in 'fast' mode)
    ocr_elements: List[UIElement] = []
    t0 = time.perf_counter()
    if mode in {"balanced", "deep"}:
        ocr_elements = extract_ocr_elements(screen_image, use_cache=True, offset=offset)
    timings["ocr_ms"] = round((time.perf_counter() - t0) * 1000.0, 2)

    # 3. CV Control Detection (Only in 'deep' mode, or 'balanced' when UI elements are sparse)
    cv_elements: List[UIElement] = []
    t0 = time.perf_counter()
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
    timings["cv_ms"] = round((time.perf_counter() - t0) * 1000.0, 2)

    # 4. Merge, deduplicate, and sort
    t0 = time.perf_counter()
    merged = deduplicate_and_merge_elements(uia_elements, ocr_elements, cv_elements, mode=mode)
    sorted_elements = sort_elements_reading_order(merged)[:max_elements]

    # Assign sequential numeric IDs starting at 1
    for idx, el in enumerate(sorted_elements, start=1):
        el.id = idx
    timings["merge_ms"] = round((time.perf_counter() - t0) * 1000.0, 2)

    raw_path = None
    annotated_path = None

    t0 = time.perf_counter()
    if screenshots_dir and os.path.exists(screenshots_dir):
        raw_path = os.path.join(screenshots_dir, f"{obs_id}.png")
        screen_image.save(raw_path)

        if save_annotated:
            annotated_img = annotate_elements(screen_image, sorted_elements)
            annotated_path = os.path.join(screenshots_dir, f"{obs_id}_marked.png")
            annotated_img.save(annotated_path)
    timings["save_ms"] = round((time.perf_counter() - t0) * 1000.0, 2)

    timings["total_ms"] = round((time.perf_counter() - t_start) * 1000.0, 2)
    logger.debug("Observation %s [%s] completed in %.1f ms: %s", obs_id, mode, timings["total_ms"], timings)

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
