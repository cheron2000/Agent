"""Instruction-conditioned visual grounding subsystem for desktop UI controls.

Provides on-demand visual grounding when UIA and OCR lack confidence or when
locating unlabeled icon-only controls.

Architectural principles:
- Strict separation of concerns: Generates grounded coordinate candidates only;
  never issues mouse or keyboard events.
- Graceful degradation: Uses Florence-2-base if torch/transformers are installed,
  with automatic fallback to OpenCV contour/visual detection.
- Coordinate safety: Clamps all boxes to physical display boundaries and
  discards out-of-bounds or invalid candidates.
"""

from dataclasses import dataclass, field
import logging
from typing import Any, Dict, List, Optional, Tuple
from PIL import Image

try:
    from .coords import box_center, clamp_box, get_screen_size
except ImportError:
    from coords import box_center, clamp_box, get_screen_size

logger = logging.getLogger("eyes.visual_grounding")


@dataclass
class GroundingCandidate:
    """A grounded visual candidate corresponding to an instruction query."""
    box: List[int]
    center: Tuple[int, int]
    confidence: float
    label: str
    source: str
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "box": self.box,
            "center": list(self.center),
            "confidence": round(self.confidence, 3),
            "label": self.label,
            "source": self.source,
            "metadata": self.metadata,
        }


class VisualGroundingBackend:
    """Abstract interface for instruction-conditioned visual grounding backends."""
    name: str = "base"

    def is_available(self) -> bool:
        return False

    def ground(
        self,
        image: Image.Image,
        instruction: str,
        offset: Tuple[int, int] = (0, 0),
    ) -> List[GroundingCandidate]:
        raise NotImplementedError


class Florence2GroundingBackend(VisualGroundingBackend):
    """Florence-2-base phrase grounding backend for natural language targets."""
    name = "florence2"

    def __init__(self, model_id: str = "microsoft/Florence-2-base", device: Optional[str] = None):
        self.model_id = model_id
        self._device = device
        self._model = None
        self._processor = None
        self._initialized = False

    def is_available(self) -> bool:
        try:
            import torch
            import transformers
            return True
        except ImportError:
            return False

    def _ensure_model(self) -> bool:
        if self._initialized:
            return self._model is not None

        self._initialized = True
        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoProcessor

            if self._device is None:
                self._device = "cuda" if torch.cuda.is_available() else "cpu"

            torch_dtype = torch.float16 if self._device == "cuda" else torch.float32

            logger.info("Loading Florence-2 visual grounding model on %s (%s)...", self._device, torch_dtype)
            self._model = AutoModelForCausalLM.from_pretrained(
                self.model_id,
                torch_dtype=torch_dtype,
                trust_remote_code=True,
            ).to(self._device).eval()

            self._processor = AutoProcessor.from_pretrained(self.model_id, trust_remote_code=True)
            return True
        except Exception as ex:
            logger.warning("Could not initialize Florence-2 visual model: %s", ex)
            self._model = None
            self._processor = None
            return False

    def ground(
        self,
        image: Image.Image,
        instruction: str,
        offset: Tuple[int, int] = (0, 0),
    ) -> List[GroundingCandidate]:
        if not self.is_available() or not self._ensure_model():
            return []

        try:
            import torch

            task_prompt = "<CAPTION_TO_PHRASE_GROUNDING>"
            prompt = f"{task_prompt}{instruction}"

            inputs = self._processor(text=prompt, images=image, return_tensors="pt")
            if self._device == "cuda":
                inputs = {k: v.to(self._device) for k, v in inputs.items()}

            with torch.no_grad():
                generated_ids = self._model.generate(
                    input_ids=inputs["input_ids"],
                    pixel_values=inputs.get("pixel_values"),
                    max_new_tokens=1024,
                    num_beams=3,
                )

            generated_text = self._processor.batch_decode(generated_ids, skip_special_tokens=False)[0]
            parsed_answer = self._processor.post_process_generation(
                generated_text,
                task=task_prompt,
                image_size=(image.width, image.height),
            )

            results: List[GroundingCandidate] = []
            grounding_data = parsed_answer.get(task_prompt, {})
            bboxes = grounding_data.get("bboxes", [])
            labels = grounding_data.get("labels", [])

            for idx, raw_box in enumerate(bboxes):
                label = labels[idx] if idx < len(labels) else instruction
                box = [
                    int(raw_box[0] + offset[0]),
                    int(raw_box[1] + offset[1]),
                    int(raw_box[2] + offset[0]),
                    int(raw_box[3] + offset[1]),
                ]
                center = box_center(box)
                results.append(
                    GroundingCandidate(
                        box=box,
                        center=center,
                        confidence=0.88,
                        label=label,
                        source=self.name,
                    )
                )

            return results
        except Exception as ex:
            logger.warning("Florence-2 inference failed for instruction '%s': %s", instruction, ex)
            return []


class CVGroundingBackend(VisualGroundingBackend):
    """Lightweight visual control grounding using OpenCV edge/contour analysis."""
    name = "cv_control"

    def is_available(self) -> bool:
        try:
            import cv2
            return True
        except ImportError:
            return False

    def ground(
        self,
        image: Image.Image,
        instruction: str,
        offset: Tuple[int, int] = (0, 0),
    ) -> List[GroundingCandidate]:
        try:
            from .cv_detect import detect_visual_controls
        except ImportError:
            try:
                from cv_detect import detect_visual_controls
            except ImportError:
                return []

        controls = detect_visual_controls(image, max_elements=40)
        candidates: List[GroundingCandidate] = []

        clean_inst = instruction.strip().lower()

        for c in controls:
            box = [
                int(c.box[0] + offset[0]),
                int(c.box[1] + offset[1]),
                int(c.box[2] + offset[0]),
                int(c.box[3] + offset[1]),
            ]
            center = box_center(box)

            # Assign heuristic confidence based on aspect ratio and control role
            conf = 0.65 if c.role == "Button" else 0.50
            candidates.append(
                GroundingCandidate(
                    box=box,
                    center=center,
                    confidence=conf,
                    label=f"Visual_{c.role}",
                    source=self.name,
                    metadata={"shape": c.role},
                )
            )

        return candidates


class InstructionGrounder:
    """Composite visual grounder that ranks candidates and enforces screen boundaries."""

    def __init__(self, backends: Optional[List[VisualGroundingBackend]] = None):
        self.backends = backends or [
            Florence2GroundingBackend(),
            CVGroundingBackend(),
        ]

    def ground_target(
        self,
        image: Image.Image,
        instruction: str,
        offset: Tuple[int, int] = (0, 0),
        min_confidence: float = 0.4,
    ) -> List[GroundingCandidate]:
        """
        Locate candidate screen elements matching natural language instruction.
        Clamps boxes to screen bounds and filters out invalid geometries.
        """
        screen_w, screen_h = get_screen_size()
        candidates: List[GroundingCandidate] = []

        for backend in self.backends:
            if backend.is_available():
                results = backend.ground(image, instruction, offset=offset)
                if results:
                    candidates.extend(results)
                    # If high-confidence semantic model responded, avoid falling back to noisy generic contours
                    if any(c.confidence >= 0.8 for c in results):
                        break

        # Post-process: Validate and clamp bounding boxes
        valid_candidates: List[GroundingCandidate] = []
        for c in candidates:
            clamped = clamp_box(c.box, screen_w, screen_h)
            width = clamped[2] - clamped[0]
            height = clamped[3] - clamped[1]

            # Reject collapsed or absurdly oversized boxes
            if width < 4 or height < 4:
                continue
            if width > (screen_w * 0.98) and height > (screen_h * 0.98):
                continue
            if c.confidence < min_confidence:
                continue

            c.box = clamped
            c.center = box_center(clamped)
            valid_candidates.append(c)

        # Sort by confidence descending
        valid_candidates.sort(key=lambda x: x.confidence, reverse=True)
        return valid_candidates
