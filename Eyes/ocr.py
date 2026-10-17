"""Tuned OCR element extraction with preprocessing, inversion, and phrase grouping."""

import logging
from typing import Any, Dict, List, Optional, Tuple
import cv2
import numpy as np
import pytesseract
from PIL import Image

try:
    from .schema import UIElement
except ImportError:
    from schema import UIElement


logger = logging.getLogger("eyes.ocr")


def preprocess_image_for_ocr(
    img: Image.Image,
    scale: float = 2.0,
    invert_dark_theme: bool = True,
) -> Tuple[np.ndarray, float]:
    """Preprocess PIL Image: convert to OpenCV BGR, grayscale, auto-invert dark themes, upscale."""
    bgr = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)

    # Invert dark-themed backgrounds so text is consistently dark-on-light for Tesseract
    if invert_dark_theme and gray.mean() < 115:
        gray = cv2.bitwise_not(gray)

    if scale != 1.0:
        gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)

    return gray, scale


def extract_ocr_elements(
    image: Image.Image,
    min_confidence: int = 40,
    scale: float = 2.0,
    offset: Tuple[int, int] = (0, 0),
    psm: int = 11,
) -> List[UIElement]:
    """Run tuned Tesseract OCR, extract word bounding boxes, and group into line phrases."""
    processed, used_scale = preprocess_image_for_ocr(image, scale=scale)
    config = f"--psm {psm}"

    try:
        data: Dict[str, Any] = pytesseract.image_to_data(
            processed,
            config=config,
            output_type=pytesseract.Output.DICT,
        )
    except Exception as e:
        logger.warning("OCR image_to_data failed: %s", e)
        return []

    off_x, off_y = offset
    raw_words = []
    n_boxes = len(data.get("text", []))

    for i in range(n_boxes):
        text = str(data["text"][i]).strip()
        conf = float(data["conf"][i]) if "conf" in data else 0.0

        if not text or conf < min_confidence:
            continue

        left = (data["left"][i] / used_scale) + off_x
        top = (data["top"][i] / used_scale) + off_y
        width = data["width"][i] / used_scale
        height = data["height"][i] / used_scale

        if width < 3 or height < 3:
            continue

        raw_words.append({
            "text": text,
            "conf": conf / 100.0,
            "box": [int(left), int(top), int(left + width), int(top + height)],
            "line_key": (data["block_num"][i], data["par_num"][i], data["line_num"][i]),
        })

    # Group adjacent words on the same line into multi-word phrases
    elements: List[UIElement] = []
    lines: Dict[Tuple[int, int, int], List[Dict[str, Any]]] = {}
    for word in raw_words:
        lines.setdefault(word["line_key"], []).append(word)

    for line_key, words in lines.items():
        # Sort words left to right
        words.sort(key=lambda w: w["box"][0])

        current_phrase: List[str] = []
        current_box: Optional[List[int]] = None
        current_confs: List[float] = []

        for w in words:
            if not current_phrase:
                current_phrase = [w["text"]]
                current_box = list(w["box"])
                current_confs = [w["conf"]]
                continue

            # If gap between words is small (less than 1.5x word height), merge into same phrase
            prev_x2 = current_box[2]
            curr_x1 = w["box"][0]
            avg_h = (current_box[3] - current_box[1])

            if (curr_x1 - prev_x2) <= max(20, avg_h * 1.5):
                current_phrase.append(w["text"])
                current_box[2] = max(current_box[2], w["box"][2])
                current_box[3] = max(current_box[3], w["box"][3])
                current_box[1] = min(current_box[1], w["box"][1])
                current_confs.append(w["conf"])
            else:
                # Flush previous phrase
                elements.append(
                    UIElement(
                        id=0,
                        role="Text",
                        name=" ".join(current_phrase),
                        box=list(current_box),
                        enabled=True,
                        source="ocr",
                        conf=float(np.mean(current_confs)),
                    )
                )
                current_phrase = [w["text"]]
                current_box = list(w["box"])
                current_confs = [w["conf"]]

        if current_phrase and current_box:
            elements.append(
                UIElement(
                    id=0,
                    role="Text",
                    name=" ".join(current_phrase),
                    box=list(current_box),
                    enabled=True,
                    source="ocr",
                    conf=float(np.mean(current_confs)),
                )
            )

    return elements
