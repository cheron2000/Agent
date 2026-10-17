"""Action expectations, intent definitions, and risk classification contracts.

Defines the contract between planned desktop actions and verifiable postconditions:
- ActionState: State machine lifecycle (PREPARED -> DISPATCHED -> VERIFYING -> CONFIRMED/FAILED/UNCERTAIN).
- ActionRiskLevel: Distinguishes safe/repeatable actions from dangerous/non-idempotent ones.
- ActionExpectation: Ground-truth postconditions required to declare an action successful.
- ActionIntent: Action specification with payload redaction for passwords and sensitive inputs.
"""

from dataclasses import dataclass, field
from enum import Enum
import time
from typing import Any, Callable, Dict, Optional


class ActionRiskLevel(str, Enum):
    """Transactional risk and idempotency classification."""
    SAFE_REPEATABLE = "safe_repeatable"    # Clicks on navigation tabs, window focus, scrolling, read-only
    NON_IDEMPOTENT = "non_idempotent"      # Submitting payment, sending messages, deleting data, terminal writes
    SENSITIVE = "sensitive"                # Passwords, tokens, private credentials


class ActionState(str, Enum):
    """Lifecycle state machine for a desktop action."""
    PREPARED = "prepared"
    DISPATCHED = "dispatched"
    VERIFYING = "verifying"
    CONFIRMED = "confirmed"
    FAILED = "failed"
    UNCERTAIN = "uncertain"
    RECOVERING = "recovering"


@dataclass
class ActionExpectation:
    """Expected observable evidence confirming that an action succeeded."""
    expected_window_title: Optional[str] = None
    expected_text: Optional[str] = None
    disallowed_text: Optional[str] = None
    expected_element_name: Optional[str] = None
    expected_element_role: Optional[str] = None
    timeout_s: float = 5.0
    risk_level: ActionRiskLevel = ActionRiskLevel.SAFE_REPEATABLE
    is_sensitive: bool = False
    description: str = ""
    custom_predicate: Optional[Callable[[Dict[str, Any], Dict[str, Any]], bool]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "expected_window_title": self.expected_window_title,
            "expected_text": self.expected_text,
            "disallowed_text": self.disallowed_text,
            "expected_element_name": self.expected_element_name,
            "expected_element_role": self.expected_element_role,
            "timeout_s": self.timeout_s,
            "risk_level": self.risk_level.value if isinstance(self.risk_level, Enum) else str(self.risk_level),
            "is_sensitive": self.is_sensitive,
            "description": self.description,
        }


@dataclass
class ActionIntent:
    """A fully specified action request with parameters, risk level, and expectation."""
    action_type: str
    target_id: Optional[int] = None
    target_query: Optional[str] = None
    parameters: Dict[str, Any] = field(default_factory=dict)
    expectation: Optional[ActionExpectation] = None
    risk_level: ActionRiskLevel = ActionRiskLevel.SAFE_REPEATABLE
    state: ActionState = ActionState.PREPARED
    is_sensitive: bool = False
    intent_id: Optional[str] = None
    created_at: float = field(default_factory=time.time)

    def sanitized_parameters(self) -> Dict[str, Any]:
        """Return parameters dictionary with sensitive fields redacted."""
        if not self.is_sensitive:
            return dict(self.parameters)
        sanitized = dict(self.parameters)
        for key in ["text", "password", "token", "secret", "value"]:
            if key in sanitized:
                sanitized[key] = "***REDACTED***"
        return sanitized

    def to_dict(self) -> Dict[str, Any]:
        return {
            "intent_id": self.intent_id,
            "action_type": self.action_type,
            "target_id": self.target_id,
            "target_query": self.target_query,
            "parameters": self.sanitized_parameters(),
            "expectation": self.expectation.to_dict() if self.expectation else None,
            "risk_level": self.risk_level.value if isinstance(self.risk_level, Enum) else str(self.risk_level),
            "state": self.state.value if isinstance(self.state, Enum) else str(self.state),
            "is_sensitive": self.is_sensitive,
            "created_at": self.created_at,
        }
