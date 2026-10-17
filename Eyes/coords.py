"""DPI awareness, coordinate normalization, and geometric utilities for Eyes."""

import ctypes
from typing import List, Optional, Tuple

_DPI_INITIALIZED = False


def init_dpi_awareness() -> None:
    """Initialize Windows high-DPI awareness (per-monitor DPI aware)."""
    global _DPI_INITIALIZED
    if _DPI_INITIALIZED:
        return
    try:
        # 2 = PROCESS_PER_MONITOR_DPI_AWARE
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        _DPI_INITIALIZED = True
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
            _DPI_INITIALIZED = True
        except Exception:
            pass


# Automatically initialize DPI awareness upon import
init_dpi_awareness()


def get_screen_size() -> Tuple[int, int]:
    """Return primary display resolution in physical pixels (width, height)."""
    try:
        w = ctypes.windll.user32.GetSystemMetrics(0)
        h = ctypes.windll.user32.GetSystemMetrics(1)
        if w > 0 and h > 0:
            return int(w), int(h)
    except Exception:
        pass
    return 1920, 1080


def box_center(box: List[int]) -> Tuple[int, int]:
    """Calculate center coordinate (cx, cy) from bounding box [x1, y1, x2, y2]."""
    x1, y1, x2, y2 = box
    return int((x1 + x2) / 2), int((y1 + y2) / 2)


def clamp_box(box: List[int], max_w: int, max_h: int) -> List[int]:
    """Clamp bounding box [x1, y1, x2, y2] to within [0, 0, max_w, max_h]."""
    x1, y1, x2, y2 = box
    x1 = max(0, min(int(x1), max_w))
    y1 = max(0, min(int(y1), max_h))
    x2 = max(x1, min(int(x2), max_w))
    y2 = max(y1, min(int(y2), max_h))
    return [x1, y1, x2, y2]


def box_area(box: List[int]) -> int:
    """Calculate area of bounding box [x1, y1, x2, y2]."""
    x1, y1, x2, y2 = box
    return max(0, x2 - x1) * max(0, y2 - y1)


def box_iou(boxA: List[int], boxB: List[int]) -> float:
    """Calculate Intersection over Union (IoU) of two bounding boxes."""
    xA = max(boxA[0], boxB[0])
    yA = max(boxA[1], boxB[1])
    xB = min(boxA[2], boxB[2])
    yB = min(boxA[3], boxB[3])

    inter_w = max(0, xB - xA)
    inter_h = max(0, yB - yA)
    inter_area = inter_w * inter_h
    if inter_area <= 0:
        return 0.0

    areaA = box_area(boxA)
    areaB = box_area(boxB)
    union_area = float(areaA + areaB - inter_area)
    if union_area <= 0:
        return 0.0
    return inter_area / union_area
