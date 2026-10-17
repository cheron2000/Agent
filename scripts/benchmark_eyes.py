"""
Benchmark script for the Eyes Perception Engine.
Measures latency (median, p95), memory usage, and component breakdowns.
"""

import os
import sys
import time
import tracemalloc
from pathlib import Path
from typing import Callable, Dict, List, Any
import numpy as np

# Ensure workspace root and Eyes are on path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "Eyes"))

import eyes
from Eyes.coords import get_screen_size
from Eyes.uia import extract_uia_elements, get_foreground_hwnd
from Eyes.ocr import preprocess_image_for_ocr, extract_ocr_elements
from Eyes.cv_detect import detect_visual_controls
from Eyes.observe import build_observation


def time_function(fn: Callable, *args, **kwargs) -> Tuple[float, Any]:
    t0 = time.perf_counter()
    res = fn(*args, **kwargs)
    t1 = time.perf_counter()
    return (t1 - t0) * 1000.0, res  # ms


def calculate_stats(timings: List[float]) -> Dict[str, float]:
    arr = np.array(timings)
    return {
        "median_ms": round(float(np.median(arr)), 2),
        "mean_ms": round(float(np.mean(arr)), 2),
        "p95_ms": round(float(np.percentile(arr, 95)), 2),
        "min_ms": round(float(np.min(arr)), 2),
        "max_ms": round(float(np.max(arr)), 2),
    }


def run_benchmark(iterations: int = 5, verbose: bool = True) -> Dict[str, Any]:
    print(f"=== Running Eyes Pipeline Benchmark ({iterations} iterations) ===")
    print(f"Screen resolution: {get_screen_size()}")
    print("-" * 60)

    tracemalloc.start()

    # 1. Screenshot Capture
    capture_timings = []
    sample_images = []
    for _ in range(iterations):
        t, img = time_function(eyes._grab_screen)
        capture_timings.append(t)
        sample_images.append(img)
    screen_img = sample_images[0]

    # 2. UIA Extraction
    hwnd = get_foreground_hwnd()
    uia_timings = []
    uia_counts = []
    for _ in range(iterations):
        t, elems = time_function(extract_uia_elements, hwnd=hwnd, max_elements=100)
        uia_timings.append(t)
        uia_counts.append(len(elems))

    # 3. OCR Preprocessing
    ocr_prep_timings = []
    for _ in range(iterations):
        t, _ = time_function(preprocess_image_for_ocr, screen_img)
        ocr_prep_timings.append(t)

    # 4. OCR Extraction
    ocr_timings = []
    ocr_counts = []
    for _ in range(iterations):
        t, elems = time_function(extract_ocr_elements, screen_img)
        ocr_timings.append(t)
        ocr_counts.append(len(elems))

    # 5. CV Detection
    cv_timings = []
    cv_counts = []
    for _ in range(iterations):
        t, elems = time_function(detect_visual_controls, screen_img)
        cv_timings.append(t)
        cv_counts.append(len(elems))

    # 6. Full Observe: Fast Mode (UIA only, no OCR/CV)
    obs_fast_timings = []
    for _ in range(iterations):
        t, res = time_function(eyes.observe, save_annotated=False, mode="fast")
        obs_fast_timings.append(t)

    # 7. Full Observe: Balanced Mode (save_annotated=False)
    obs_raw_timings = []
    obs_elements = []
    for _ in range(iterations):
        t, res = time_function(eyes.observe, save_annotated=False, mode="balanced")
        obs_raw_timings.append(t)
        obs_elements.append(len(res.get("elements", [])))

    # 8. Full Observe: Balanced Mode (save_annotated=True)
    obs_ann_timings = []
    for _ in range(iterations):
        t, res = time_function(eyes.observe, save_annotated=True, mode="balanced")
        obs_ann_timings.append(t)

    # 9. Full Observe: Deep Mode (full CV edge contours)
    obs_deep_timings = []
    for _ in range(iterations):
        t, res = time_function(eyes.observe, save_annotated=False, mode="deep")
        obs_deep_timings.append(t)

    current_mem, peak_mem = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    # Clean up any generated screenshots
    shots_dir = ROOT / "Eyes" / "screenshots"
    for p in shots_dir.glob("*.png"):
        try:
            p.unlink()
        except Exception:
            pass

    from Eyes.ocr import get_ocr_cache_stats
    cache_stats = get_ocr_cache_stats()

    results = {
        "capture": calculate_stats(capture_timings),
        "uia": {**calculate_stats(uia_timings), "elements": int(np.mean(uia_counts))},
        "ocr_preprocess": calculate_stats(ocr_prep_timings),
        "ocr_extract": {**calculate_stats(ocr_timings), "elements": int(np.mean(ocr_counts))},
        "cv_detect": {**calculate_stats(cv_timings), "elements": int(np.mean(cv_counts))},
        "observe_fast": calculate_stats(obs_fast_timings),
        "observe_balanced_raw": {**calculate_stats(obs_raw_timings), "elements": int(np.mean(obs_elements))},
        "observe_balanced_annotated": calculate_stats(obs_ann_timings),
        "observe_deep": calculate_stats(obs_deep_timings),
        "cache_stats": cache_stats,
        "peak_memory_mb": round(peak_mem / (1024 * 1024), 2),
    }

    if verbose:
        print(f"{'Component':<28} | {'Median (ms)':<12} | {'P95 (ms)':<10} | {'Details'}")
        print("-" * 75)
        print(f"{'Screenshot Capture':<28} | {results['capture']['median_ms']:<12} | {results['capture']['p95_ms']:<10} | Direct Screen Grab")
        print(f"{'UIA Accessibility':<28} | {results['uia']['median_ms']:<12} | {results['uia']['p95_ms']:<10} | {results['uia']['elements']} elements")
        print(f"{'OCR Preprocessing':<28} | {results['ocr_preprocess']['median_ms']:<12} | {results['ocr_preprocess']['p95_ms']:<10} | Direct RGB->Gray")
        print(f"{'OCR Extraction':<28} | {results['ocr_extract']['median_ms']:<12} | {results['ocr_extract']['p95_ms']:<10} | {results['ocr_extract']['elements']} elements")
        print(f"{'CV Control Detection':<28} | {results['cv_detect']['median_ms']:<12} | {results['cv_detect']['p95_ms']:<10} | {results['cv_detect']['elements']} elements")
        print("-" * 75)
        print(f"{'Observe Fast (UIA-only)':<28} | {results['observe_fast']['median_ms']:<12} | {results['observe_fast']['p95_ms']:<10} | Lowest latency")
        print(f"{'Observe Balanced (unannotated)':<28} | {results['observe_balanced_raw']['median_ms']:<12} | {results['observe_balanced_raw']['p95_ms']:<10} | {results['observe_balanced_raw']['elements']} total")
        print(f"{'Observe Balanced (annotated)':<28} | {results['observe_balanced_annotated']['median_ms']:<12} | {results['observe_balanced_annotated']['p95_ms']:<10} | Marked Set-of-Marks")
        print(f"{'Observe Deep (UIA+OCR+CV)':<28} | {results['observe_deep']['median_ms']:<12} | {results['observe_deep']['p95_ms']:<10} | Comprehensive perception")
        print("-" * 75)
        print(f"Peak Python Memory: {results['peak_memory_mb']} MB")
        print(f"OCR Cache Hits: {cache_stats['hits']}, Misses: {cache_stats['misses']}, Hit Rate: {cache_stats['hit_rate']}")
        print("=" * 75)

    return results


if __name__ == "__main__":
    from typing import Tuple
    run_benchmark(iterations=5)
