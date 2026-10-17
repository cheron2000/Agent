"""Visual change detection, frame diffing, and polling synchronization."""

import time
from typing import Callable, Optional
import cv2
import numpy as np
from PIL import Image

try:
    from .schema import UIElement
except ImportError:
    from schema import UIElement



def compute_frame_difference(img1: Image.Image, img2: Image.Image) -> float:
    """Compute normalized mean absolute difference between two images using downscaled frames.
    
    Returns a float between 0.0 (identical) and 1.0 (completely different).
    """
    g1 = cv2.cvtColor(np.array(img1), cv2.COLOR_RGB2GRAY)
    g2 = cv2.cvtColor(np.array(img2), cv2.COLOR_RGB2GRAY)

    # Downscale to 64x36 for instant, noise-resistant visual change comparison
    s1 = cv2.resize(g1, (64, 36), interpolation=cv2.INTER_AREA)
    s2 = cv2.resize(g2, (64, 36), interpolation=cv2.INTER_AREA)

    diff = cv2.absdiff(s1, s2)
    return float(diff.mean() / 255.0)


def has_screen_changed(img1: Image.Image, img2: Image.Image, threshold: float = 0.015) -> bool:
    """Check if the desktop visual state has meaningfully changed."""
    return compute_frame_difference(img1, img2) >= threshold


def wait_until(
    condition_fn: Callable[[], bool],
    timeout_s: float = 5.0,
    poll_interval_s: float = 0.2,
) -> bool:
    """Poll condition_fn until it returns True, or until timeout_s is exceeded."""
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout_s:
        try:
            if condition_fn():
                return True
        except Exception:
            pass
        time.sleep(poll_interval_s)
    return False
