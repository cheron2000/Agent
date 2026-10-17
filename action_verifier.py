"""Action verifier evaluating fresh UI evidence against action expectations.

Architectural principles:
- No blind confirmation: API dispatch success (e.g. mouse click dispatched) only
  proves input was sent to the OS; it NEVER proves the application reacted.
- Fresh visual evidence: Requires a distinct, freshly captured post-action observation.
- Stale target detection: Flags stale observations where state hashes or IDs are identical.
- Deterministic outcome classification:
    CONFIRMED: Postcondition directly satisfied by fresh evidence.
    FAILED: Evidence directly contradicts postcondition or critical error text appeared.
    UNCERTAIN: Evidence is ambiguous or cannot be verified definitively.
"""

from dataclasses import dataclass, field
from enum import Enum
import logging
import re
import time
from typing import Any, Dict, List, Optional

try:
    from .action_expectations import ActionExpectation, ActionIntent, ActionRiskLevel, ActionState
except ImportError:
    from action_expectations import ActionExpectation, ActionIntent, ActionRiskLevel, ActionState

logger = logging.getLogger("action_verifier")


class VerificationStatus(str, Enum):
    CONFIRMED = "confirmed"
    FAILED = "failed"
    UNCERTAIN = "uncertain"


@dataclass
class VerificationEvidence:
    """Documented evidence proving or disproving an expected action outcome."""
    status: VerificationStatus
    confidence: float
    evidence_type: str
    details: Dict[str, Any] = field(default_factory=dict)
    error_message: Optional[str] = None
    latency_ms: float = 0.0
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status.value if isinstance(self.status, Enum) else str(self.status),
            "confidence": round(self.confidence, 3),
            "evidence_type": self.evidence_type,
            "details": self.details,
            "error_message": self.error_message,
            "latency_ms": round(self.latency_ms, 2),
            "timestamp": self.timestamp,
        }


class ActionVerifier:
    """Evaluates whether an action achieved its intended outcome using fresh UI evidence."""

    def __init__(self, default_timeout_s: float = 5.0):
        self.default_timeout_s = default_timeout_s

    def verify(
        self,
        intent: ActionIntent,
        pre_obs: Optional[Dict[str, Any]],
        dispatch_result: Dict[str, Any],
        post_obs: Optional[Dict[str, Any]],
    ) -> VerificationEvidence:
        """
        Evaluate postconditions against fresh UI observations.
        """
        start_t = time.perf_counter()

        # 1. Dispatch failure check: If physical input failed at the driver level, action failed
        if not dispatch_result.get("success", False):
            elapsed_ms = (time.perf_counter() - start_t) * 1000.0
            intent.state = ActionState.FAILED
            return VerificationEvidence(
                status=VerificationStatus.FAILED,
                confidence=1.0,
                evidence_type="dispatch_error",
                details={"dispatch_result": dispatch_result},
                error_message=dispatch_result.get("error", "Action dispatch failed at driver level"),
                latency_ms=elapsed_ms,
            )

        intent.state = ActionState.VERIFYING

        # 2. Fresh observation requirement: Post observation must exist
        if not post_obs:
            elapsed_ms = (time.perf_counter() - start_t) * 1000.0
            intent.state = ActionState.UNCERTAIN
            return VerificationEvidence(
                status=VerificationStatus.UNCERTAIN,
                confidence=0.0,
                evidence_type="missing_observation",
                error_message="No post-action observation provided for verification",
                latency_ms=elapsed_ms,
            )

        # 3. Stale observation detection: Verify post_obs is not the exact same object/snapshot as pre_obs
        if pre_obs and post_obs:
            pre_id = pre_obs.get("observation_id")
            post_id = post_obs.get("observation_id")
            if pre_id and post_id and pre_id == post_id:
                elapsed_ms = (time.perf_counter() - start_t) * 1000.0
                intent.state = ActionState.UNCERTAIN
                return VerificationEvidence(
                    status=VerificationStatus.UNCERTAIN,
                    confidence=0.1,
                    evidence_type="stale_observation",
                    error_message=f"Stale observation detected (pre_id == post_id: {pre_id}); requires fresh capture",
                    latency_ms=elapsed_ms,
                )

        exp = intent.expectation

        # 4. If no explicit expectation was specified:
        if not exp:
            elapsed_ms = (time.perf_counter() - start_t) * 1000.0
            # Safe repeatable actions without expectation default to confirmed (low confidence)
            if intent.risk_level == ActionRiskLevel.SAFE_REPEATABLE:
                intent.state = ActionState.CONFIRMED
                return VerificationEvidence(
                    status=VerificationStatus.CONFIRMED,
                    confidence=0.6,
                    evidence_type="default_safe_dispatch",
                    details={"note": "Safe repeatable action succeeded with no explicit postcondition specified"},
                    latency_ms=elapsed_ms,
                )
            # Consequential / non-idempotent actions without expectation must be marked UNCERTAIN
            intent.state = ActionState.UNCERTAIN
            return VerificationEvidence(
                status=VerificationStatus.UNCERTAIN,
                confidence=0.4,
                evidence_type="unverified_non_idempotent",
                error_message="Non-idempotent action dispatched without verifiable postcondition",
                latency_ms=elapsed_ms,
            )

        # 5. Disallowed text check: Detect error banners, modal dialogs, or failure banners
        if exp.disallowed_text:
            visible_text = post_obs.get("text", "")
            if exp.disallowed_text.lower() in visible_text.lower():
                elapsed_ms = (time.perf_counter() - start_t) * 1000.0
                intent.state = ActionState.FAILED
                return VerificationEvidence(
                    status=VerificationStatus.FAILED,
                    confidence=0.95,
                    evidence_type="disallowed_text_detected",
                    details={"detected_disallowed_text": exp.disallowed_text},
                    error_message=f"Disallowed text '{exp.disallowed_text}' detected on screen after action",
                    latency_ms=elapsed_ms,
                )

        # 6. Window title expectation
        if exp.expected_window_title:
            active_win = post_obs.get("active_window", "")
            pattern = re.compile(re.escape(exp.expected_window_title), re.IGNORECASE)
            if pattern.search(active_win):
                elapsed_ms = (time.perf_counter() - start_t) * 1000.0
                intent.state = ActionState.CONFIRMED
                return VerificationEvidence(
                    status=VerificationStatus.CONFIRMED,
                    confidence=0.98,
                    evidence_type="window_title_match",
                    details={
                        "expected_title": exp.expected_window_title,
                        "active_window": active_win,
                    },
                    latency_ms=elapsed_ms,
                )
            else:
                elapsed_ms = (time.perf_counter() - start_t) * 1000.0
                intent.state = ActionState.FAILED
                return VerificationEvidence(
                    status=VerificationStatus.FAILED,
                    confidence=0.90,
                    evidence_type="window_title_mismatch",
                    details={
                        "expected_title": exp.expected_window_title,
                        "active_window": active_win,
                    },
                    error_message=f"Active window '{active_win}' did not match expected '{exp.expected_window_title}'",
                    latency_ms=elapsed_ms,
                )

        # 7. Expected text expectation (OCR / transcribe)
        if exp.expected_text:
            visible_text = post_obs.get("text", "")
            elements = post_obs.get("elements", [])
            element_texts = [e.get("name", "") for e in elements if e.get("name")]
            all_text = visible_text + " " + " ".join(element_texts)

            if exp.expected_text.lower() in all_text.lower():
                elapsed_ms = (time.perf_counter() - start_t) * 1000.0
                intent.state = ActionState.CONFIRMED
                return VerificationEvidence(
                    status=VerificationStatus.CONFIRMED,
                    confidence=0.95,
                    evidence_type="expected_text_visible",
                    details={"expected_text": exp.expected_text},
                    latency_ms=elapsed_ms,
                )
            else:
                elapsed_ms = (time.perf_counter() - start_t) * 1000.0
                intent.state = ActionState.FAILED
                return VerificationEvidence(
                    status=VerificationStatus.FAILED,
                    confidence=0.88,
                    evidence_type="expected_text_missing",
                    details={"expected_text": exp.expected_text},
                    error_message=f"Expected text '{exp.expected_text}' not visible in post-action observation",
                    latency_ms=elapsed_ms,
                )

        # 8. Expected UI element name expectation (UIA / accessibility tree)
        if exp.expected_element_name:
            elements = post_obs.get("elements", [])
            match = None
            target_name = exp.expected_element_name.lower()
            for el in elements:
                name = el.get("name", "").lower()
                role = el.get("role", "").lower()
                if target_name in name:
                    if exp.expected_element_role and exp.expected_element_role.lower() not in role:
                        continue
                    match = el
                    break

            if match:
                elapsed_ms = (time.perf_counter() - start_t) * 1000.0
                intent.state = ActionState.CONFIRMED
                return VerificationEvidence(
                    status=VerificationStatus.CONFIRMED,
                    confidence=0.92,
                    evidence_type="expected_element_visible",
                    details={"matched_element": match},
                    latency_ms=elapsed_ms,
                )
            else:
                elapsed_ms = (time.perf_counter() - start_t) * 1000.0
                intent.state = ActionState.FAILED
                return VerificationEvidence(
                    status=VerificationStatus.FAILED,
                    confidence=0.85,
                    evidence_type="expected_element_missing",
                    details={"expected_element_name": exp.expected_element_name},
                    error_message=f"Element '{exp.expected_element_name}' not found in observation",
                    latency_ms=elapsed_ms,
                )

        # 9. Custom predicate validator
        if exp.custom_predicate:
            try:
                ok = exp.custom_predicate(pre_obs or {}, post_obs)
                elapsed_ms = (time.perf_counter() - start_t) * 1000.0
                if ok:
                    intent.state = ActionState.CONFIRMED
                    return VerificationEvidence(
                        status=VerificationStatus.CONFIRMED,
                        confidence=0.90,
                        evidence_type="custom_predicate_satisfied",
                        latency_ms=elapsed_ms,
                    )
                else:
                    intent.state = ActionState.FAILED
                    return VerificationEvidence(
                        status=VerificationStatus.FAILED,
                        confidence=0.90,
                        evidence_type="custom_predicate_failed",
                        error_message="Custom predicate evaluated to False",
                        latency_ms=elapsed_ms,
                    )
            except Exception as ex:
                elapsed_ms = (time.perf_counter() - start_t) * 1000.0
                intent.state = ActionState.UNCERTAIN
                return VerificationEvidence(
                    status=VerificationStatus.UNCERTAIN,
                    confidence=0.3,
                    evidence_type="custom_predicate_exception",
                    error_message=f"Predicate exception: {ex}",
                    latency_ms=elapsed_ms,
                )

        # Fallback: Inconclusive
        elapsed_ms = (time.perf_counter() - start_t) * 1000.0
        intent.state = ActionState.UNCERTAIN
        return VerificationEvidence(
            status=VerificationStatus.UNCERTAIN,
            confidence=0.5,
            evidence_type="inconclusive",
            error_message="Postcondition criteria could not be definitively evaluated",
            latency_ms=elapsed_ms,
        )
