"""Goal decomposition schemas, DAG execution contracts, and compensation definitions.

Provides:
- StepCompensation: Reversible inverse operations (closing dialogs, clearing fields, restoring values).
- PlanStep: Atomic, dependency-tracked step with preconditions, expected evidence, and risk levels.
- ExecutionPlan: DAG plan containing steps, dependency validation, and serialization.
- GoalStatus: Lifecycle status of multi-step autonomous tasks.
"""

from dataclasses import dataclass, field
from enum import Enum
import time
from typing import Any, Dict, List, Optional, Set


class GoalStatus(str, Enum):
    PENDING = "pending"
    PLANNING = "planning"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    COMPENSATING = "compensating"
    COMPENSATED = "compensated"
    ABORTED = "aborted"


class StepExecutionState(str, Enum):
    PENDING = "pending"
    DISPATCHING = "dispatching"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    COMPENSATED = "compensated"


@dataclass
class StepCompensation:
    """An inverse or compensatory action executed to restore previous GUI state on plan failure."""
    action_type: str                   # "press_key", "hotkey", "click", "type_text"
    parameters: Dict[str, Any] = field(default_factory=dict)
    description: str = ""
    is_reversible: bool = True
    executed: bool = False
    success: Optional[bool] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action_type": self.action_type,
            "parameters": self.parameters,
            "description": self.description,
            "is_reversible": self.is_reversible,
            "executed": self.executed,
            "success": self.success,
        }


@dataclass
class PlanStep:
    """An atomic DAG execution step with explicit dependencies, expectations, and risk classification."""
    step_id: str
    action_type: str
    target_query: Optional[str] = None
    parameters: Dict[str, Any] = field(default_factory=dict)
    dependencies: List[str] = field(default_factory=list)
    expected_window_title: Optional[str] = None
    expected_text: Optional[str] = None
    disallowed_text: Optional[str] = None
    risk_level: str = "safe_repeatable"     # "safe_repeatable", "non_idempotent", "sensitive"
    timeout_s: float = 10.0
    status: StepExecutionState = StepExecutionState.PENDING
    compensation: Optional[StepCompensation] = None
    retries_allowed: int = 1
    retry_count: int = 0
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_id": self.step_id,
            "action_type": self.action_type,
            "target_query": self.target_query,
            "parameters": self.parameters,
            "dependencies": list(self.dependencies),
            "expected_window_title": self.expected_window_title,
            "expected_text": self.expected_text,
            "disallowed_text": self.disallowed_text,
            "risk_level": self.risk_level,
            "timeout_s": self.timeout_s,
            "status": self.status.value if isinstance(self.status, Enum) else str(self.status),
            "compensation": self.compensation.to_dict() if self.compensation else None,
            "retries_allowed": self.retries_allowed,
            "retry_count": self.retry_count,
            "error_message": self.error_message,
            "metadata": self.metadata,
        }


@dataclass
class ExecutionPlan:
    """Directed Acyclic Graph (DAG) plan for multi-step desktop tasks."""
    goal_id: str
    instruction: str
    steps: List[PlanStep] = field(default_factory=list)
    status: GoalStatus = GoalStatus.PENDING
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def get_step(self, step_id: str) -> Optional[PlanStep]:
        for s in self.steps:
            if s.step_id == step_id:
                return s
        return None

    def get_completed_step_ids(self) -> Set[str]:
        return {s.step_id for s in self.steps if s.status == StepExecutionState.COMPLETED}

    def get_next_eligible_step(self) -> Optional[PlanStep]:
        """Find the next pending step whose dependencies are all satisfied."""
        completed = self.get_completed_step_ids()
        for s in self.steps:
            if s.status == StepExecutionState.PENDING:
                if all(dep in completed for dep in s.dependencies):
                    return s
        return None

    def validate_dag(self) -> Tuple[bool, Optional[str]]:
        """Verify plan contains no circular dependencies and all dependency IDs exist."""
        all_ids = {s.step_id for s in self.steps}
        # Check unknown dependencies
        for s in self.steps:
            for dep in s.dependencies:
                if dep not in all_ids:
                    return False, f"Step '{s.step_id}' references unknown dependency '{dep}'"
                if dep == s.step_id:
                    return False, f"Step '{s.step_id}' cannot depend on itself"

        # Check cycles via Kahn's algorithm or DFS
        visited = set()
        rec_stack = set()

        def has_cycle(curr: str) -> bool:
            visited.add(curr)
            rec_stack.add(curr)
            step = self.get_step(curr)
            if step:
                for dep in step.dependencies:
                    if dep not in visited:
                        if has_cycle(dep):
                            return True
                    elif dep in rec_stack:
                        return True
            rec_stack.remove(curr)
            return False

        for s in self.steps:
            if s.step_id not in visited:
                if has_cycle(s.step_id):
                    return False, f"Circular dependency cycle detected involving step '{s.step_id}'"

        return True, None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "goal_id": self.goal_id,
            "instruction": self.instruction,
            "status": self.status.value if isinstance(self.status, Enum) else str(self.status),
            "steps": [s.to_dict() for s in self.steps],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "metadata": self.metadata,
        }
