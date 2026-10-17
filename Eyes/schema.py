"""Data schemas for UI elements and full screen observations."""

from dataclasses import dataclass, field
import threading
import time
from typing import Any, Dict, List, Literal, Optional, Tuple, Union

try:
    from .coords import box_center
except (ImportError, ValueError):
    from Eyes.coords import box_center



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
        if self.box and len(self.box) >= 4 and (not self.center or self.center == (0, 0)):
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
    mode: str = "balanced"
    timings: Dict[str, float] = field(default_factory=dict)
    scene_graph: Optional[Any] = None

    def get_scene_graph(self) -> Any:
        if self.scene_graph is not None:
            return self.scene_graph
        try:
            from .scene_graph import build_scene_graph
        except (ImportError, ValueError):
            from Eyes.scene_graph import build_scene_graph
        self.scene_graph = build_scene_graph(
            self.elements,
            active_window=self.active_window,
            observation_id=self.observation_id,
        )
        return self.scene_graph

    def get_element(self, element_id: Union[int, str]) -> Optional[UIElement]:
        try:
            target_id = int(element_id)
        except (ValueError, TypeError):
            target_id = element_id
        for el in self.elements:
            if el.id == target_id:
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

    def to_compact_dict(self) -> Dict[str, Any]:
        """Compact representation optimized for LLM token efficiency."""
        return {
            "observation_id": self.observation_id,
            "active_window": self.active_window,
            "mode": self.mode,
            "element_count": len(self.elements),
            "elements": [
                {
                    "id": el.id,
                    "role": el.role,
                    "name": el.name,
                    "box": list(el.box),
                    "center": list(el.center),
                }
                for el in self.elements
            ],
            "screen_size": list(self.screen_size),
            "timings": dict(self.timings),
        }

    def to_dict(self, compact: bool = False) -> Dict[str, Any]:
        if compact:
            return self.to_compact_dict()
        return {
            "observation_id": self.observation_id,
            "active_window": self.active_window,
            "mode": self.mode,
            "element_count": len(self.elements),
            "elements": [el.to_dict() for el in self.elements],
            "image": self.annotated_image_path or self.image_path,
            "image_path": self.image_path,
            "annotated_image": self.annotated_image_path,
            "annotated_image_path": self.annotated_image_path,
            "screen_size": list(self.screen_size),
            "created_at": self.created_at,
            "timings": dict(self.timings),
        }


# â”€â”€ Observation Store / Cache (Bounded & Thread-Safe) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
_MAX_OBSERVATIONS_HISTORY = 10
_CURRENT_OBSERVATION: Optional[Observation] = None
_OBSERVATIONS_HISTORY: Dict[str, Observation] = {}
_OBS_LOCK = threading.Lock()


def set_current_observation(obs: Observation) -> None:
    """Store the most recent observation in memory and update bounded history."""
    global _CURRENT_OBSERVATION
    with _OBS_LOCK:
        _CURRENT_OBSERVATION = obs
        _OBSERVATIONS_HISTORY[obs.observation_id] = obs
        # Prune oldest if history exceeds bound
        while len(_OBSERVATIONS_HISTORY) > _MAX_OBSERVATIONS_HISTORY:
            oldest_key = next(iter(_OBSERVATIONS_HISTORY))
            del _OBSERVATIONS_HISTORY[oldest_key]


def get_current_observation() -> Optional[Observation]:
    """Retrieve the most recent observation from memory."""
    with _OBS_LOCK:
        return _CURRENT_OBSERVATION


def get_observation_by_id(observation_id: str) -> Optional[Observation]:
    """Retrieve a specific observation by ID from the bounded history."""
    with _OBS_LOCK:
        return _OBSERVATIONS_HISTORY.get(observation_id)


def clear_observation_history() -> None:
    """Clear all observation cache and history."""
    global _CURRENT_OBSERVATION
    with _OBS_LOCK:
        _CURRENT_OBSERVATION = None
        _OBSERVATIONS_HISTORY.clear()


def resolve_element(element_id: Union[int, str], observation_id: Optional[str] = None) -> Optional[UIElement]:
    """Resolve an element ID safely from a target or current observation."""
    with _OBS_LOCK:
        target_obs = None
        if observation_id:
            target_obs = _OBSERVATIONS_HISTORY.get(observation_id)
            if not target_obs:
                return None
        else:
            target_obs = _CURRENT_OBSERVATION

        if not target_obs:
            return None
        return target_obs.get_element(element_id)


