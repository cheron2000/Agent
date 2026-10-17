"""Data structures, schemas, and contracts for Human-Like Step Planning.

Incorporates:
- Atomic Action Contract with preconditions, effects, and risk classification.
- 4-Tier Verification Contract (Direct State, Visual Grounding, Semantic, Escalation).
- Recovery Provenance Contract for structured auditability and error forensics.
- Durable Workflow Checkpointing for crash-resilient task resumption.
"""

from dataclasses import dataclass, field
import datetime
from enum import Enum
import json
import os
import time
from typing import Any, Dict, List, Optional
import uuid


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


class ActionRiskLevel(str, Enum):
    """Safety and transactional risk classification for planned actions."""
    READ_ONLY = "read_only"              # Inspecting, observing, zooming, reading text
    IDEMPOTENT = "idempotent"            # Focusing window, switching tabs, selecting address bar
    CONSEQUENTIAL = "consequential"      # Typing search query, submitting form, navigating URL
    DESTRUCTIVE = "destructive"          # Deleting files, modifying permissions, irreversible writes


class VerificationLevel(str, Enum):
    """Deterministic verification hierarchy to prevent false success declarations."""
    DIRECT_STATE = "direct_state"        # Level 1: UIA property, window handle/title, control state
    VISUAL_GROUNDING = "visual_grounding"# Level 2: Fine-tuned OCR, element box bounding, Set-of-Marks
    SEMANTIC = "semantic"                # Level 3: Cognitive context reasoning against user goal
    HUMAN_ESCALATION = "human_escalation"# Level 4: Escalation when ambiguous or destructive action occurs


class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    RECOVERED = "recovered"


@dataclass
class RecoveryProvenanceRecord:
    """Structured audit trail documenting step execution, failure reasons, and recovery."""
    workflow_id: str
    step_number: int
    attempt_id: int
    pre_state_hash: Optional[str] = None
    action_type: str = ""
    parameters: Dict[str, Any] = field(default_factory=dict)
    failure_reason: Optional[str] = None
    recovery_strategy: Optional[str] = None   # 'micro_retry', 'macro_replan', 'human_escalate'
    post_condition_satisfied: bool = False
    visual_evidence: Optional[str] = None
    burst_time_ms: float = 0.0
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "workflow_id": self.workflow_id,
            "step_number": self.step_number,
            "attempt_id": self.attempt_id,
            "pre_state_hash": self.pre_state_hash,
            "action_type": self.action_type,
            "parameters": self.parameters,
            "failure_reason": self.failure_reason,
            "recovery_strategy": self.recovery_strategy,
            "post_condition_satisfied": self.post_condition_satisfied,
            "visual_evidence": self.visual_evidence,
            "burst_time_ms": self.burst_time_ms,
            "timestamp": self.timestamp,
        }


@dataclass
class Checkpoint:
    """Durable state snapshot enabling interrupted workflows to resume safely."""
    checkpoint_id: str
    workflow_id: str
    step_number: int
    completed_steps: List[int]
    active_window: str
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "checkpoint_id": self.checkpoint_id,
            "workflow_id": self.workflow_id,
            "step_number": self.step_number,
            "completed_steps": self.completed_steps,
            "active_window": self.active_window,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }


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
    risk_level: ActionRiskLevel = ActionRiskLevel.IDEMPOTENT
    verification_level: VerificationLevel = VerificationLevel.VISUAL_GROUNDING
    preconditions: Dict[str, Any] = field(default_factory=dict)
    expected_effects: Dict[str, Any] = field(default_factory=dict)
    retry_budget: int = 2
    provenance_records: List[RecoveryProvenanceRecord] = field(default_factory=list)

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
            "risk_level": self.risk_level.value if isinstance(self.risk_level, ActionRiskLevel) else str(self.risk_level),
            "verification_level": self.verification_level.value if isinstance(self.verification_level, VerificationLevel) else str(self.verification_level),
            "preconditions": self.preconditions,
            "expected_effects": self.expected_effects,
            "retry_budget": self.retry_budget,
            "provenance_records": [r.to_dict() for r in self.provenance_records],
        }


@dataclass
class Plan:
    """A multi-step human-like plan to accomplish a high-level desktop goal."""
    goal: str
    workflow_id: str = field(default_factory=lambda: f"wf_{int(time.time())}_{uuid.uuid4().hex[:6]}")
    steps: List[PlanStep] = field(default_factory=list)
    current_step: int = 0
    total_burst_time_ms: float = 0.0
    completed: bool = False
    checkpoints: List[Checkpoint] = field(default_factory=list)
    provenance_log: List[RecoveryProvenanceRecord] = field(default_factory=list)

    def add_step(
        self,
        intent: str,
        action_type: StepActionType,
        parameters: Optional[Dict[str, Any]] = None,
        expected_outcome: str = "",
        utterance: str = "",
        risk_level: ActionRiskLevel = ActionRiskLevel.IDEMPOTENT,
        verification_level: VerificationLevel = VerificationLevel.VISUAL_GROUNDING,
        preconditions: Optional[Dict[str, Any]] = None,
        expected_effects: Optional[Dict[str, Any]] = None,
        retry_budget: int = 2,
    ) -> PlanStep:
        step = PlanStep(
            step_number=len(self.steps) + 1,
            intent=intent,
            action_type=action_type,
            parameters=parameters or {},
            expected_outcome=expected_outcome,
            utterance=utterance,
            risk_level=risk_level,
            verification_level=verification_level,
            preconditions=preconditions or {},
            expected_effects=expected_effects or {},
            retry_budget=retry_budget,
        )
        self.steps.append(step)
        return step

    def record_provenance(self, record: RecoveryProvenanceRecord) -> None:
        self.provenance_log.append(record)
        # Also append to the corresponding step if valid
        if 1 <= record.step_number <= len(self.steps):
            self.steps[record.step_number - 1].provenance_records.append(record)

    def save_checkpoint(self, directory: str = ".checkpoints", active_window: str = "") -> str:
        """Persist workflow state snapshot after a verified state transition."""
        os.makedirs(directory, exist_ok=True)
        completed_ids = [s.step_number for s in self.steps if s.status in {StepStatus.COMPLETED, StepStatus.RECOVERED}]
        cp = Checkpoint(
            checkpoint_id=f"cp_{self.workflow_id}_{self.current_step}",
            workflow_id=self.workflow_id,
            step_number=self.current_step,
            completed_steps=completed_ids,
            active_window=active_window,
            metadata={"goal": self.goal, "total_burst_time_ms": self.total_burst_time_ms},
        )
        self.checkpoints.append(cp)

        filepath = os.path.join(directory, f"{self.workflow_id}.json")
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)
        return filepath

    @classmethod
    def load_checkpoint(cls, filepath: str) -> "Plan":
        """Reconstruct a plan from a durable checkpoint file."""
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        plan = cls(
            goal=data["goal"],
            workflow_id=data.get("workflow_id", ""),
            current_step=data.get("current_step", 0),
            total_burst_time_ms=data.get("total_burst_time_ms", 0.0),
            completed=data.get("completed", False),
        )

        for s_data in data.get("steps", []):
            step = PlanStep(
                step_number=s_data["step_number"],
                intent=s_data["intent"],
                action_type=StepActionType(s_data["action_type"]),
                parameters=s_data.get("parameters", {}),
                expected_outcome=s_data.get("expected_outcome", ""),
                status=StepStatus(s_data.get("status", "pending")),
                burst_time_ms=s_data.get("burst_time_ms", 0.0),
                utterance=s_data.get("utterance", ""),
                evidence=s_data.get("evidence"),
                error=s_data.get("error"),
                risk_level=ActionRiskLevel(s_data.get("risk_level", "idempotent")),
                verification_level=VerificationLevel(s_data.get("verification_level", "visual_grounding")),
                preconditions=s_data.get("preconditions", {}),
                expected_effects=s_data.get("expected_effects", {}),
                retry_budget=s_data.get("retry_budget", 2),
            )
            plan.steps.append(step)

        return plan

    def to_dict(self) -> Dict[str, Any]:
        return {
            "workflow_id": self.workflow_id,
            "goal": self.goal,
            "total_steps": len(self.steps),
            "current_step": self.current_step,
            "completed": self.completed,
            "total_burst_time_ms": self.total_burst_time_ms,
            "steps": [s.to_dict() for s in self.steps],
            "checkpoints": [c.to_dict() for c in self.checkpoints],
            "provenance_count": len(self.provenance_log),
        }
