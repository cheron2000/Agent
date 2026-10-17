import hashlib
import logging
import os
import shutil
import threading
from collections import OrderedDict
from typing import Any, Dict, List, Optional, Tuple, Union
import cv2
import numpy as np
import pytesseract
from PIL import Image

try:
    from .schema import UIElement
except (ImportError, ValueError):
    from Eyes.schema import UIElement


logger = logging.getLogger("eyes.ocr")

TESSERACT_PATHS = [
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    r"C:\Users\Lenovo\AppData\Local\Programs\Tesseract-OCR\tesseract.exe",
    os.path.expanduser(r"~\AppData\Local\Programs\Tesseract-OCR\tesseract.exe"),
]


def _find_tesseract() -> Optional[str]:
    """Locate the Tesseract executable on Windows or system PATH."""
    for p in TESSERACT_PATHS:
        if os.path.exists(p):
            return p
    return shutil.which("tesseract")


# ── Bounded Thread-Safe LRU Cache for OCR Extraction ────────────────────────
_MAX_OCR_CACHE_SIZE = 16
_OCR_CACHE: OrderedDict = OrderedDict()
_CACHE_STATS = {"hits": 0, "misses": 0}
_TESSERACT_AVAILABLE: Optional[bool] = None
_OCR_CACHE_LOCK = threading.Lock()


def is_tesseract_available() -> bool:
    """Check and cache whether Tesseract OCR binary is reachable and operational."""
    global _TESSERACT_AVAILABLE
    with _OCR_CACHE_LOCK:
        if _TESSERACT_AVAILABLE is not None:
            return _TESSERACT_AVAILABLE

        # Ensure pytesseract points to a valid binary if available on disk
        cmd = getattr(pytesseract.pytesseract, "tesseract_cmd", "tesseract")
        if not cmd or cmd == "tesseract" or not os.path.exists(cmd):
            discovered = _find_tesseract()
            if discovered:
                pytesseract.pytesseract.tesseract_cmd = discovered

        try:
            ver = pytesseract.get_tesseract_version()
            _TESSERACT_AVAILABLE = bool(ver)
        except Exception:
            _TESSERACT_AVAILABLE = False
        return _TESSERACT_AVAILABLE


def get_ocr_cache_stats() -> Dict[str, Any]:
    """Return cache hit/miss statistics and current cache size."""
    with _OCR_CACHE_LOCK:
        total = _CACHE_STATS["hits"] + _CACHE_STATS["misses"]
        hit_rate = round(_CACHE_STATS["hits"] / total, 3) if total > 0 else 0.0
        return {
            "hits": _CACHE_STATS["hits"],
            "misses": _CACHE_STATS["misses"],
            "size": len(_OCR_CACHE),
            "hit_rate": hit_rate,
        }


def clear_ocr_cache() -> None:
    """Explicitly clear the OCR LRU cache and reset availability state."""
    global _TESSERACT_AVAILABLE
    with _OCR_CACHE_LOCK:
        _OCR_CACHE.clear()
        _CACHE_STATS["hits"] = 0
        _CACHE_STATS["misses"] = 0
        _TESSERACT_AVAILABLE = None


def _compute_image_hash(img: Union[Image.Image, np.ndarray]) -> str:
    """Generate a fast perceptual-style content hash of the image for cache keying."""
    try:
        if isinstance(img, np.ndarray):
            # Rescale array to a fixed small thumbnail to prevent 1-pixel collisions on small crops
            if img.size == 0:
                return ""
            if len(img.shape) == 3:
                gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY if img.shape[2] == 3 else cv2.COLOR_BGRA2GRAY)
            else:
                gray = img
            thumb = cv2.resize(gray, (64, 36), interpolation=cv2.INTER_NEAREST)
            sample = thumb.tobytes()
        else:
            # Thumbnail sample
            thumb = img.resize((64, 36), Image.Resampling.NEAREST).convert("L")
            sample = thumb.tobytes()
        return hashlib.md5(sample).hexdigest()
    except Exception:
        return ""


def preprocess_image_for_ocr(
    img: Union[Image.Image, np.ndarray],
    scale: float = 2.0,
    invert_dark_theme: bool = True,
    interpolation: int = cv2.INTER_LINEAR,
) -> Tuple[np.ndarray, float]:
    """Preprocess image: convert directly to grayscale, auto-invert dark themes, upscale."""
    if isinstance(img, np.ndarray):
        if len(img.shape) == 2:
            gray = img.copy()
        elif img.shape[2] == 1:
            gray = img[:, :, 0].copy()
        elif img.shape[2] == 3:
            gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
        elif img.shape[2] == 4:
            gray = cv2.cvtColor(img, cv2.COLOR_RGBA2GRAY)
        else:
            gray = img.copy()
    else:
        # Convert PIL Image reliably to grayscale mode 'L'
        gray = np.array(img.convert("L"))

    # Invert dark-themed backgrounds so text is consistently dark-on-light for Tesseract
    if invert_dark_theme and gray.mean() < 115:
        gray = cv2.bitwise_not(gray)

    if scale != 1.0:
        gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=interpolation)

    return gray, scale


def extract_ocr_elements(
    image: Union[Image.Image, np.ndarray],
    min_confidence: int = 40,
    scale: float = 2.0,
    offset: Union[Tuple[int, int], List[int]] = (0, 0),
    psm: int = 11,
    interpolation: int = cv2.INTER_LINEAR,
    use_cache: bool = True,
) -> List[UIElement]:
    """Run tuned Tesseract OCR with caching, bounding box extraction, and line phrase grouping."""
    if not is_tesseract_available():
        return []

    norm_offset = (int(offset[0]), int(offset[1])) if offset and len(offset) >= 2 else (0, 0)

    # Check LRU cache
    img_hash = _compute_image_hash(image) if use_cache else ""
    cache_key = (img_hash, round(scale, 2), psm, min_confidence, norm_offset)
    if use_cache and img_hash:
        with _OCR_CACHE_LOCK:
            if cache_key in _OCR_CACHE:
                _CACHE_STATS["hits"] += 1
                _OCR_CACHE.move_to_end(cache_key)
                cached_elements = _OCR_CACHE[cache_key]
                # Return shallow copies so caller mutations don't alter cached objects
                return [
                    UIElement(
                        id=el.id,
                        role=el.role,
                        name=el.name,
                        box=list(el.box),
                        center=el.center,
                        enabled=el.enabled,
                        source=el.source,
                        conf=el.conf,
                    )
                    for el in cached_elements
                ]
            else:
                _CACHE_STATS["misses"] += 1

    processed, used_scale = preprocess_image_for_ocr(image, scale=scale, interpolation=interpolation)
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

    off_x, off_y = norm_offset
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
            if not current_phrase or current_box is None:
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
                current_box[0] = min(current_box[0], w["box"][0])
                current_box[1] = min(current_box[1], w["box"][1])
                current_box[2] = max(current_box[2], w["box"][2])
                current_box[3] = max(current_box[3], w["box"][3])
                current_confs.append(w["conf"])
            else:
                # Flush previous phrase
                avg_conf = (sum(current_confs) / len(current_confs)) if current_confs else 0.0
                elements.append(
                    UIElement(
                        id=0,
                        role="Text",
                        name=" ".join(current_phrase),
                        box=list(current_box),
                        enabled=True,
                        source="ocr",
                        conf=round(avg_conf, 3),
                    )
                )
                current_phrase = [w["text"]]
                current_box = list(w["box"])
                current_confs = [w["conf"]]

        if current_phrase and current_box:
            avg_conf = (sum(current_confs) / len(current_confs)) if current_confs else 0.0
            elements.append(
                UIElement(
                    id=0,
                    role="Text",
                    name=" ".join(current_phrase),
                    box=list(current_box),
                    enabled=True,
                    source="ocr",
                    conf=round(avg_conf, 3),
                )
            )

    # Store in LRU cache if caching is active
    if use_cache and img_hash:
        with _OCR_CACHE_LOCK:
            _OCR_CACHE[cache_key] = elements
            while len(_OCR_CACHE) > _MAX_OCR_CACHE_SIZE:
                _OCR_CACHE.popitem(last=False)

    return elements
