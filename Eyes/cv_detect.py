"""Computer Vision fallback: contour rectangle detection and template matching."""

import logging
from typing import List, Optional, Tuple, Union
import cv2
import numpy as np
from PIL import Image

try:
    from .schema import UIElement
except ImportError:
    from schema import UIElement


logger = logging.getLogger("eyes.cv_detect")


def detect_visual_controls(
    image: Union[Image.Image, np.ndarray],
    min_size: Tuple[int, int] = (16, 16),
    max_size: Tuple[int, int] = (800, 500),
    offset: Tuple[int, int] = (0, 0),
    max_elements: int = 100,
) -> List[UIElement]:
    """Detect visual control rectangles (buttons, inputs, icons) using edge contours."""
    if isinstance(image, np.ndarray):
        if len(image.shape) == 2:
            gray = image
        elif image.shape[2] == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
        elif image.shape[2] == 4:
            gray = cv2.cvtColor(image, cv2.COLOR_RGBA2GRAY)
        else:
            gray = image
    else:
        arr = np.array(image)
        if len(arr.shape) == 2:
            gray = arr
        elif arr.shape[2] == 3:
            gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
        else:
            gray = cv2.cvtColor(arr, cv2.COLOR_RGBA2GRAY)

    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blurred, 50, 150)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    closed = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel)

    contours, _ = cv2.findContours(closed, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)

    off_x, off_y = offset
    elements: List[UIElement] = []
    min_w, min_h = min_size
    max_w, max_h = max_size

    for cnt in contours:
        if len(elements) >= max_elements:
            break
        x, y, w, h = cv2.boundingRect(cnt)
        if w < min_w or h < min_h or w > max_w or h > max_h:
            continue

        aspect_ratio = float(w) / float(h)
        if aspect_ratio < 0.15 or aspect_ratio > 15.0:
            continue

        box = [int(x + off_x), int(y + off_y), int(x + w + off_x), int(y + h + off_y)]
        elements.append(
            UIElement(
                id=0,
                role="Control",
                name="",
                box=box,
                enabled=True,
                source="cv",
                conf=0.75,
            )
        )

    return elements


def match_template(
    screen_image: Image.Image,
    template_image: Image.Image,
    threshold: float = 0.85,
    role: str = "Icon",
    name: str = "Template",
) -> List[UIElement]:
    """Find occurrences of a visual template within the screen image."""
    screen_bgr = cv2.cvtColor(np.array(screen_image), cv2.COLOR_RGB2BGR)
    tpl_bgr = cv2.cvtColor(np.array(template_image), cv2.COLOR_RGB2BGR)

    th, tw = tpl_bgr.shape[:2]
    res = cv2.matchTemplate(screen_bgr, tpl_bgr, cv2.TM_CCOEFF_NORMED)
    loc = np.where(res >= threshold)

    elements: List[UIElement] = []
    for pt in zip(*loc[::-1]):
        elements.append(
            UIElement(
                id=0,
                role=role,
                name=name,
                box=[int(pt[0]), int(pt[1]), int(pt[0] + tw), int(pt[1] + th)],
                enabled=True,
                source="cv",
                conf=float(res[pt[1], pt[0]]),
            )
        )

    return elements
