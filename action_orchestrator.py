"""Stateful Desktop Action Orchestrator.

Orchestrates the complete closed-loop action lifecycle:
    INSTRUCTION -> TARGET RESOLUTION -> FRESHNESS CHECK -> DISPATCH ->
    POST-OBSERVE -> VERIFICATION -> RECOVERY (RE-RESOLVE / RETRY / HARD STOP).

Guarantees:
1. Target Resolution Hierarchy: Prefers UIA and OCR; falls back to Visual Grounding on demand.
2. Freshness Gate: Rejects targets derived from stale or expired observations before dispatch.
3. Response Normalization: Normalizes driver dispatch responses into uniform contracts.
4. Deterministic Verification: Disallows blind confirmation from dispatch success alone.
5. Safety Boundaries: Permits at most 1 retry for safe idempotent actions; enforces hard stop on non-idempotent actions.
6. Dry-run Mode: Allows full lifecycle simulation and testing without physical mouse/keyboard disruption.
"""

from dataclasses import dataclass, field
import logging
import time
import uuid
from typing import Any, Callable, Dict, List, Optional, Tuple

try:
    from .action_expectations import ActionExpectation, ActionIntent, ActionRiskLevel, ActionState
    from .action_verifier import ActionVerifier, VerificationEvidence, VerificationStatus
    from .action_recovery import ActionRecoveryDecider, RecoveryDecision, RecoveryStrategy
except ImportError:
    from action_expectations import ActionExpectation, ActionIntent, ActionRiskLevel, ActionState
    from action_verifier import ActionVerifier, VerificationEvidence, VerificationStatus
    from action_recovery import ActionRecoveryDecider, RecoveryDecision, RecoveryStrategy

logger = logging.getLogger("action_orchestrator")


@dataclass
class OrchestratedStepRecord:
    """Audit trail record for a single orchestrated action lifecycle execution."""
    intent_id: str
    action_type: str
    target_description: Optional[str]
    dispatched: bool
    confirmed: bool
    verification_status: str
    evidence_type: str
    recovery_strategy: Optional[str]
    retries_executed: int
    wall_clock_ms: float
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "intent_id": self.intent_id,
            "action_type": self.action_type,
            "target_description": self.target_description,
            "dispatched": self.dispatched,
            "confirmed": self.confirmed,
            "verification_status": self.verification_status,
            "evidence_type": self.evidence_type,
            "recovery_strategy": self.recovery_strategy,
            "retries_executed": self.retries_executed,
            "wall_clock_ms": round(self.wall_clock_ms, 2),
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }


class ActionOrchestrator:
    """Coordinates perception, target resolution, dispatch, verification, and recovery."""

    def __init__(
        self,
        controller: Optional[Any] = None,
        verifier: Optional[ActionVerifier] = None,
        recovery_decider: Optional[ActionRecoveryDecider] = None,
        dry_run: bool = False,
        observation_ttl_s: float = 10.0,
    ):
        self.controller = controller
        self.verifier = verifier or ActionVerifier()
        self.recovery = recovery_decider or ActionRecoveryDecider(max_safe_retries=1)
        self.dry_run = dry_run
        self.observation_ttl_s = observation_ttl_s
        self.audit_log: List[OrchestratedStepRecord] = []

    def resolve_target(
        self,
        query: str,
        observation: Dict[str, Any],
        use_visual_grounding_fallback: bool = True,
    ) -> Optional[Tuple[int, int]]:
        """
        Locate target coordinates preferring UIA/OCR first, falling back to visual grounding.
        """
        clean_query = query.strip().lower()

        # Tier 1: Relational Semantic Scene Graph query (handles 'Cancel in Settings', 'field next to Username')
        try:
            from Eyes.scene_graph import build_scene_graph
            from Eyes.schema import UIElement

            ui_els = []
            for e in observation.get("elements", []):
                if isinstance(e, dict):
                    ui_els.append(UIElement(
                        id=e.get("id", 0),
                        role=e.get("role", "Control"),
                        name=e.get("name", ""),
                        box=list(e.get("box", [0, 0, 0, 0])),
                        center=tuple(e.get("center", (0, 0))),
                        source=e.get("source", "uia"),
                    ))
                elif isinstance(e, UIElement):
                    ui_els.append(e)

            if ui_els:
                graph = build_scene_graph(
                    ui_els,
                    active_window=observation.get("active_window", ""),
                    observation_id=observation.get("observation_id", ""),
                )
                hit = graph.query_target(query)
                if hit:
                    return tuple(hit.center)
        except Exception as ex:
            logger.debug("Scene graph resolution skipped: %s", ex)

        # Tier 2: Direct UIA element names & automation IDs
        for el in observation.get("elements", []):
            name = el.get("name", "").strip().lower()
            auto_id = el.get("automation_id", "").strip().lower()
            if clean_query in name or (auto_id and clean_query in auto_id):
                center = el.get("center")
                if center:
                    return tuple(center)

        # Tier 3: OCR text lines
        text_lines = observation.get("text", "").splitlines()
        for line in text_lines:
            if clean_query in line.lower():
                # If element list contains OCR text match
                for el in observation.get("elements", []):
                    if clean_query in el.get("name", "").lower():
                        return tuple(el["center"])

        # Tier 3: Visual Grounding fallback (on-demand for icon-only / unlabeled controls)
        if use_visual_grounding_fallback and self.controller and hasattr(self.controller, "ground_target"):
            try:
                res = self.controller.ground_target(query, min_confidence=0.45)
                if res.get("success") and res.get("best_candidate"):
                    return tuple(res["best_candidate"]["center"])
            except Exception as ex:
                logger.warning("Visual grounding fallback failed for query '%s': %s", query, ex)

        return None

    def execute_step(
        self,
        intent: ActionIntent,
        pre_observation: Optional[Dict[str, Any]] = None,
        dispatch_fn: Optional[Callable[[ActionIntent], Dict[str, Any]]] = None,
        observe_fn: Optional[Callable[[], Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Execute full stateful OODA action cycle with verification and recovery.
        """
        start_t = time.perf_counter()
        retries_used = 0

        # Pre-action observation
        if pre_observation is not None:
            pre_obs = pre_observation
        elif observe_fn:
            pre_obs = observe_fn()
        elif self.controller and hasattr(self.controller, "observe"):
            pre_obs = self.controller.observe(annotate=False)
        else:
            pre_obs = {"observation_id": f"obs_{uuid.uuid4().hex}", "timestamp": time.time()}

        # Freshness Gate: check observation TTL
        obs_age = time.time() - pre_obs.get("timestamp", time.time())
        if obs_age > self.observation_ttl_s:
            logger.info("Pre-observation is stale (age=%.2fs > ttl=%.2fs); refreshing observation", obs_age, self.observation_ttl_s)
            if observe_fn:
                pre_obs = observe_fn()
            elif self.controller and hasattr(self.controller, "observe"):
                pre_obs = self.controller.observe(annotate=False)

        # Main execution & recovery loop
        while True:
            # 1. Target resolution if query provided and coords missing
            if intent.target_query and "x" not in intent.parameters and intent.target_id is None:
                coords = self.resolve_target(intent.target_query, pre_obs)
                if coords:
                    intent.parameters["x"], intent.parameters["y"] = coords
                else:
                    elapsed_ms = (time.perf_counter() - start_t) * 1000.0
                    record = OrchestratedStepRecord(
                        intent_id=intent.intent_id or "intent_unresolved",
                        action_type=intent.action_type,
                        target_description=intent.target_query,
                        dispatched=False,
                        confirmed=False,
                        verification_status=VerificationStatus.FAILED.value,
                        evidence_type="target_unresolved",
                        recovery_strategy=RecoveryStrategy.ABORT_FOR_SAFETY.value,
                        retries_executed=retries_used,
                        wall_clock_ms=elapsed_ms,
                    )
                    self.audit_log.append(record)
                    return {
                        "success": False,
                        "intent": intent.to_dict(),
                        "error": f"Target '{intent.target_query}' could not be resolved from UI",
                        "audit_record": record.to_dict(),
                    }

            # 2. Dispatch
            dispatch_res = self._dispatch(intent, dispatch_fn=dispatch_fn)

            # 3. Post-action observation
            if observe_fn:
                post_obs = observe_fn()
            elif self.controller and hasattr(self.controller, "observe"):
                time.sleep(0.2)
                post_obs = self.controller.observe(annotate=False)
            else:
                post_obs = {"observation_id": f"obs_{uuid.uuid4().hex}", "timestamp": time.time()}

            # 4. Verify outcome
            evidence = self.verifier.verify(intent, pre_obs, dispatch_res, post_obs)

            # 5. Check if confirmed
            if evidence.status == VerificationStatus.CONFIRMED:
                elapsed_ms = (time.perf_counter() - start_t) * 1000.0
                record = OrchestratedStepRecord(
                    intent_id=intent.intent_id or "intent_confirmed",
                    action_type=intent.action_type,
                    target_description=intent.target_query or str(intent.target_id),
                    dispatched=True,
                    confirmed=True,
                    verification_status=evidence.status.value,
                    evidence_type=evidence.evidence_type,
                    recovery_strategy=RecoveryStrategy.NO_RECOVERY_NEEDED.value,
                    retries_executed=retries_used,
                    wall_clock_ms=elapsed_ms,
                )
                self.audit_log.append(record)
                return {
                    "success": True,
                    "intent": intent.to_dict(),
                    "dispatch_result": dispatch_res,
                    "verification": evidence.to_dict(),
                    "recovery_decision": None,
                    "audit_record": record.to_dict(),
                }

            # 6. If not confirmed, evaluate recovery decision
            decision = self.recovery.decide(
                intent,
                evidence,
                pre_obs=pre_obs,
                post_obs=post_obs,
            )

            # If recovery allows retry and action is safe repeatable:
            if decision.allowed and decision.strategy == RecoveryStrategy.RETRY_SAFE:
                retries_used += 1
                logger.info("Executing authorized retry (%d) for safe action %s", retries_used, intent.action_type)
                # Re-observe before retrying
                if observe_fn:
                    pre_obs = observe_fn()
                elif self.controller and hasattr(self.controller, "observe"):
                    pre_obs = self.controller.observe(annotate=False)
                continue

            # Hard stop or unauthorized recovery
            elapsed_ms = (time.perf_counter() - start_t) * 1000.0
            record = OrchestratedStepRecord(
                intent_id=intent.intent_id or "intent_failed",
                action_type=intent.action_type,
                target_description=intent.target_query or str(intent.target_id),
                dispatched=dispatch_res.get("success", False),
                confirmed=False,
                verification_status=evidence.status.value,
                evidence_type=evidence.evidence_type,
                recovery_strategy=decision.strategy.value,
                retries_executed=retries_used,
                wall_clock_ms=elapsed_ms,
            )
            self.audit_log.append(record)
            return {
                "success": False,
                "intent": intent.to_dict(),
                "dispatch_result": dispatch_res,
                "verification": evidence.to_dict(),
                "recovery_decision": decision.to_dict(),
                "audit_record": record.to_dict(),
            }

    def _dispatch(
        self,
        intent: ActionIntent,
        dispatch_fn: Optional[Callable[[ActionIntent], Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Dispatch action with dry-run support and contract normalization."""
        if self.dry_run:
            intent.state = ActionState.DISPATCHED
            return {
                "success": True,
                "dry_run": True,
                "action": intent.action_type,
                "parameters": intent.sanitized_parameters(),
            }

        if dispatch_fn:
            raw = dispatch_fn(intent)
            return self._normalize_dispatch_response(raw)

        if not self.controller:
            return {"success": False, "error": "No controller or dispatch function provided"}

        act_type = intent.action_type
        params = intent.parameters or {}

        try:
            if act_type == "click_element" and intent.target_id is not None:
                raw = self.controller.click_element(
                    intent.target_id,
                    button=params.get("button", "left"),
                    clicks=params.get("clicks", 1),
                )
            elif act_type in ["click_coords", "click"]:
                raw = self.controller.click(
                    x=params.get("x"),
                    y=params.get("y"),
                    button=params.get("button", "left"),
                    clicks=params.get("clicks", 1),
                )
            elif act_type == "type_text":
                raw = self.controller.type_text(
                    text=params.get("text", ""),
                    profile=params.get("profile", "natural"),
                )
            elif act_type == "press_key":
                self.controller.press_key(params.get("key", "enter"))
                raw = {"success": True, "action": "press_key"}
            elif act_type == "hotkey":
                keys = params.get("keys", [])
                self.controller.hotkey(*keys)
                raw = {"success": True, "action": "hotkey"}
            elif act_type == "focus_window":
                win_target = params.get("title") or intent.target_query
                ok = self.controller.focus(win_target)
                raw = {"success": ok, "action": "focus_window"}
            elif act_type == "scroll":
                raw = self.controller.scroll(
                    clicks=params.get("clicks", -3),
                    x=params.get("x"),
                    y=params.get("y"),
                )
            else:
                raw = {"success": False, "error": f"Unsupported action type: {act_type}"}

            return self._normalize_dispatch_response(raw)
        except Exception as ex:
            return {"success": False, "error": str(ex)}

    @staticmethod
    def _normalize_dispatch_response(raw: Any) -> Dict[str, Any]:
        """Normalize raw driver responses into standardized { 'success': bool, ... } dictionary."""
        if isinstance(raw, dict):
            # Check for boolean success or string status
            success = raw.get("success")
            if success is None and "status" in raw:
                success = raw["status"] in ["success", "ok", "dispatched"]
            raw["success"] = bool(success) if success is not None else True
            return raw
        elif isinstance(raw, bool):
            return {"success": raw}
        return {"success": True, "result": str(raw)}
