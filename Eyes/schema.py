"""Data schemas for UI elements and full screen observations."""

from dataclasses import asdict, dataclass, field
import threading
import time
from typing import Any, Dict, List, Literal, Optional, Tuple

try:
    from .coords import box_center
except ImportError:
    from coords import box_center



@dataclass
class UIElement:
    """Represents a discrete interactable or readable visual element."""
    id: int
    role: str
    name: str
    box: List[int]  # [x1, y1, x2, y2] in physical screen pixels
    center: Tuple[int, int] = field(default_factory=lambda: (0, 0))
    enabled: bool = True
    source: Literal["uia", "ocr", "cv"] = "uia"
    conf: float = 1.0

    def __post_init__(self):
        if not self.center or self.center == (0, 0):
            self.center = box_center(self.box)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "role": self.role,
            "name": self.name,
            "box": list(self.box),
            "center": list(self.center),
            "enabled": self.enabled,
            "source": self.source,
            "conf": round(float(self.conf), 3),
        }


@dataclass
class Observation:
    """Represents a unified visual observation of the desktop at a single point in time."""
    observation_id: str
    active_window: str
    elements: List[UIElement] = field(default_factory=list)
    image_path: Optional[str] = None
    annotated_image_path: Optional[str] = None
    screen_size: Tuple[int, int] = (1920, 1080)
    created_at: float = field(default_factory=time.time)

    def get_element(self, element_id: int) -> Optional[UIElement]:
        for el in self.elements:
            if el.id == element_id:
                return el
        return None

    def find_by_name(self, query: str, exact: bool = False) -> List[UIElement]:
        q = query.strip().lower()
        matches = []
        for el in self.elements:
            name = (el.name or "").lower()
            if (q == name) if exact else (q in name):
                matches.append(el)
        return matches

    def to_dict(self) -> Dict[str, Any]:
        return {
            "observation_id": self.observation_id,
            "active_window": self.active_window,
            "element_count": len(self.elements),
            "elements": [el.to_dict() for el in self.elements],
            "image_path": self.image_path,
            "annotated_image_path": self.annotated_image_path,
            "screen_size": list(self.screen_size),
            "created_at": self.created_at,
        }


# ── Observation Store / Cache ────────────────────────────────────────────────
_CURRENT_OBSERVATION: Optional[Observation] = None
_OBS_LOCK = threading.Lock()


def set_current_observation(obs: Observation) -> None:
    """Store the most recent observation in memory."""
    global _CURRENT_OBSERVATION
    with _OBS_LOCK:
        _CURRENT_OBSERVATION = obs


def get_current_observation() -> Optional[Observation]:
    """Retrieve the most recent observation from memory."""
    with _OBS_LOCK:
        return _CURRENT_OBSERVATION


def resolve_element(element_id: int, observation_id: Optional[str] = None) -> Optional[UIElement]:
    """Resolve an element ID from the current observation."""
    with _OBS_LOCK:
        if not _CURRENT_OBSERVATION:
            return None
        if observation_id and _CURRENT_OBSERVATION.observation_id != observation_id:
            return None
        return _CURRENT_OBSERVATION.get_element(element_id)
