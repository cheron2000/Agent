"""Data structures and schemas for Human-Like Step Planning."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class StepActionType(str, Enum):
    HOTKEY = "hotkey"
    PRESS_KEY = "press_key"
    TYPE_TEXT = "type_text"
    CLICK_ELEMENT = "click_element"
    CLICK_COORDS = "click_coords"
    MOVE_MOUSE = "move_mouse"
    FOCUS_WINDOW = "focus_window"
    WAIT = "wait"
    VERIFY = "verify"
    OBSERVE = "observe"


class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class PlanStep:
    """An individual atomic step in a human-like task plan."""
    step_number: int
    intent: str
    action_type: StepActionType
    parameters: Dict[str, Any] = field(default_factory=dict)
    expected_outcome: str = ""
    status: StepStatus = StepStatus.PENDING
    burst_time_ms: float = 0.0
    utterance: str = ""
    evidence: Optional[str] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_number": self.step_number,
            "intent": self.intent,
            "action_type": self.action_type.value if isinstance(self.action_type, StepActionType) else str(self.action_type),
            "parameters": self.parameters,
            "expected_outcome": self.expected_outcome,
            "status": self.status.value if isinstance(self.status, StepStatus) else str(self.status),
            "burst_time_ms": self.burst_time_ms,
            "utterance": self.utterance,
            "evidence": self.evidence,
            "error": self.error,
        }


@dataclass
class Plan:
    """A multi-step human-like plan to accomplish a high-level desktop goal."""
    goal: str
    steps: List[PlanStep] = field(default_factory=list)
    current_step: int = 0
    total_burst_time_ms: float = 0.0
    completed: bool = False

    def add_step(
        self,
        intent: str,
        action_type: StepActionType,
        parameters: Optional[Dict[str, Any]] = None,
        expected_outcome: str = "",
        utterance: str = "",
    ) -> PlanStep:
        step = PlanStep(
            step_number=len(self.steps) + 1,
            intent=intent,
            action_type=action_type,
            parameters=parameters or {},
            expected_outcome=expected_outcome,
            utterance=utterance,
        )
        self.steps.append(step)
        return step

    def to_dict(self) -> Dict[str, Any]:
        return {
            "goal": self.goal,
            "total_steps": len(self.steps),
            "current_step": self.current_step,
            "completed": self.completed,
            "total_burst_time_ms": self.total_burst_time_ms,
            "steps": [s.to_dict() for s in self.steps],
        }
