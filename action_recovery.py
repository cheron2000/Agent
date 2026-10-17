"""Action recovery strategy decider for failed or uncertain desktop actions.

Enforces strict safety boundaries:
1. Max 1 retry for safe, repeatable (idempotent) actions.
2. ZERO automatic retries for non-idempotent actions (payments, form submissions, deletions, chat messages).
3. Automatic target re-resolution when observation is stale or coordinates shifted.
4. Structured recovery provenance logging for transparent audit trails.
"""

from dataclasses import dataclass, field
from enum import Enum
import logging
import time
from typing import Any, Dict, List, Optional

try:
    from .action_expectations import ActionIntent, ActionRiskLevel, ActionState
    from .action_verifier import VerificationEvidence, VerificationStatus
except ImportError:
    from action_expectations import ActionIntent, ActionRiskLevel, ActionState
    from action_verifier import VerificationEvidence, VerificationStatus

logger = logging.getLogger("action_recovery")


class RecoveryStrategy(str, Enum):
    RETRY_SAFE = "retry_safe"                  # Re-dispatch safe idempotent action (max once)
    RE_RESOLVE_TARGET = "re_resolve_target"    # Re-observe screen and re-locate target
    DISMISS_MODAL = "dismiss_modal"            # Dismiss blocking dialog (ESC or cancel)
    ABORT_FOR_SAFETY = "abort_for_safety"      # Stop immediately; action is non-idempotent
    MARK_UNCERTAIN = "mark_uncertain"          # Evidence ambiguous; stop and request verification


@dataclass
class RecoveryDecision:
    """Action recovery recommendation produced by ActionRecoveryDecider."""
    strategy: RecoveryStrategy
    allowed: bool
    reason: str
    retry_count: int = 0
    next_action: Optional[ActionIntent] = None
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "strategy": self.strategy.value if isinstance(self.strategy, Enum) else str(self.strategy),
            "allowed": self.allowed,
            "reason": self.reason,
            "retry_count": self.retry_count,
            "timestamp": self.timestamp,
        }


class ActionRecoveryDecider:
    """Decides safe recovery workflows while preventing duplicate non-idempotent operations."""

    def __init__(self, max_safe_retries: int = 1):
        self.max_safe_retries = max_safe_retries
        self._action_retry_counts: Dict[str, int] = {}
        self.history: List[Dict[str, Any]] = []

    def decide(
        self,
        intent: ActionIntent,
        evidence: VerificationEvidence,
        pre_obs: Optional[Dict[str, Any]] = None,
        post_obs: Optional[Dict[str, Any]] = None,
    ) -> RecoveryDecision:
        """
        Evaluate verification evidence and return safe recovery decision.
        """
        # If action was confirmed, no recovery needed
        if evidence.status == VerificationStatus.CONFIRMED:
            return RecoveryDecision(
                strategy=RecoveryStrategy.RETRY_SAFE,
                allowed=False,
                reason="Action already confirmed; no recovery necessary",
                retry_count=0,
            )

        intent.state = ActionState.RECOVERING
        action_key = intent.intent_id or f"{intent.action_type}:{intent.target_id}:{intent.target_query}"
        current_retries = self._action_retry_counts.get(action_key, 0)

        # CRITICAL SAFETY RULE 1: Non-idempotent actions must NEVER be automatically repeated
        if intent.risk_level == ActionRiskLevel.NON_IDEMPOTENT:
            decision = RecoveryDecision(
                strategy=RecoveryStrategy.ABORT_FOR_SAFETY,
                allowed=False,
                reason=(
                    f"Refusing automatic retry for non-idempotent action '{intent.action_type}' "
                    f"(target: {intent.target_query or intent.target_id}) to prevent duplicate state corruption."
                ),
                retry_count=current_retries,
            )
            self._record(intent, evidence, decision)
            return decision

        # CRITICAL SAFETY RULE 2: Stale observation or missing post observation -> Re-resolve target
        if evidence.evidence_type in ["stale_observation", "missing_observation", "expected_element_missing"]:
            decision = RecoveryDecision(
                strategy=RecoveryStrategy.RE_RESOLVE_TARGET,
                allowed=True,
                reason="Screen state changed or element missing; re-observing to re-ground target coordinates.",
                retry_count=current_retries,
            )
            self._record(intent, evidence, decision)
            return decision

        # CRITICAL SAFETY RULE 3: Disallowed modal dialog or popup detected -> Dismiss modal
        if evidence.evidence_type == "disallowed_text_detected":
            decision = RecoveryDecision(
                strategy=RecoveryStrategy.DISMISS_MODAL,
                allowed=True,
                reason=f"Blocking UI error or dialog detected ({evidence.details.get('detected_disallowed_text')}); dismiss with ESC.",
                retry_count=current_retries,
            )
            self._record(intent, evidence, decision)
            return decision

        # CRITICAL SAFETY RULE 4: Safe repeatable action with retry budget remaining
        if intent.risk_level == ActionRiskLevel.SAFE_REPEATABLE:
            if current_retries < self.max_safe_retries:
                self._action_retry_counts[action_key] = current_retries + 1
                decision = RecoveryDecision(
                    strategy=RecoveryStrategy.RETRY_SAFE,
                    allowed=True,
                    reason=f"Action is safe and repeatable; executing retry {current_retries + 1}/{self.max_safe_retries}.",
                    retry_count=current_retries + 1,
                )
                self._record(intent, evidence, decision)
                return decision
            else:
                decision = RecoveryDecision(
                    strategy=RecoveryStrategy.MARK_UNCERTAIN,
                    allowed=False,
                    reason=f"Maximum retry limit ({self.max_safe_retries}) reached for safe action '{intent.action_type}'.",
                    retry_count=current_retries,
                )
                self._record(intent, evidence, decision)
                return decision

        # Default fallback: Mark uncertain
        decision = RecoveryDecision(
            strategy=RecoveryStrategy.MARK_UNCERTAIN,
            allowed=False,
            reason=f"Uncertain evidence for action '{intent.action_type}': {evidence.error_message}",
            retry_count=current_retries,
        )
        self._record(intent, evidence, decision)
        return decision

    def _record(self, intent: ActionIntent, evidence: VerificationEvidence, decision: RecoveryDecision):
        record = {
            "intent": intent.to_dict(),
            "evidence": evidence.to_dict(),
            "decision": decision.to_dict(),
            "timestamp": time.time(),
        }
        self.history.append(record)
        logger.info(
            "Recovery strategy for %s: %s (allowed=%s, reason=%s)",
            intent.action_type,
            decision.strategy.value,
            decision.allowed,
            decision.reason,
        )

    def reset_retries(self, intent_id: Optional[str] = None):
        """Reset retry counts for a given intent or all intents."""
        if intent_id:
            self._action_retry_counts.pop(intent_id, None)
        else:
            self._action_retry_counts.clear()
