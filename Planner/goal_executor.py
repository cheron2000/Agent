"""Autonomous Multi-Step Goal Planner and Self-Healing Executor.

Features:
- DAG Dependency Tracking: Enforces dependency ordering across multi-step plans.
- Durable Checkpointing & WAL Journaling: Survives process kills and restarts without lost state.
- Crash Reconciliation: Reconciles stranded 'DISPATCHING' steps against fresh visual evidence.
- Compensation Recovery: Reverses side-effects (closing dialogs, clearing fields) on unrecoverable failure.
- Integration: Dispatches verified atomic actions through ActionOrchestrator.
"""

from dataclasses import dataclass, field
from enum import Enum
import logging
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

try:
    from .goal_schema import ExecutionPlan, PlanStep, StepExecutionState, GoalStatus, StepCompensation
    from .checkpoint_store import SQLiteCheckpointStore
    from action_expectations import ActionExpectation, ActionIntent, ActionRiskLevel
    from action_orchestrator import ActionOrchestrator
    from action_verifier import VerificationStatus
except (ImportError, ValueError):
    from Planner.goal_schema import ExecutionPlan, PlanStep, StepExecutionState, GoalStatus, StepCompensation
    from Planner.checkpoint_store import SQLiteCheckpointStore
    from action_expectations import ActionExpectation, ActionIntent, ActionRiskLevel
    from action_orchestrator import ActionOrchestrator
    from action_verifier import VerificationStatus

logger = logging.getLogger("planner.goal_executor")

# Global re-entrant lock to serialize desktop automation across goals and prevent concurrent device contention
_DESKTOP_GOAL_LOCK = threading.RLock()


@dataclass
class GoalExecutionResult:
    """Summary of complete goal execution lifecycle."""
    goal_id: str
    status: GoalStatus
    completed_steps: List[str]
    failed_step: Optional[str] = None
    compensations_executed: List[str] = field(default_factory=list)
    wall_clock_ms: float = 0.0
    audit_trail: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "goal_id": self.goal_id,
            "status": self.status.value if isinstance(self.status, Enum) else str(self.status),
            "completed_steps": self.completed_steps,
            "failed_step": self.failed_step,
            "compensations_executed": self.compensations_executed,
            "wall_clock_ms": round(self.wall_clock_ms, 2),
            "audit_trail": self.audit_trail,
        }


class AutonomousGoalExecutor:
    """Executes multi-step plans with durable SQLite checkpointing and compensatory recovery."""

    def __init__(
        self,
        orchestrator: Optional[ActionOrchestrator] = None,
        store: Optional[SQLiteCheckpointStore] = None,
        dry_run: bool = False,
    ):
        self.orchestrator = orchestrator or ActionOrchestrator(dry_run=dry_run)
        self.store = store or SQLiteCheckpointStore()
        self.dry_run = dry_run
        self._cancelled_goals: Set[str] = set()

    def cancel_goal(self, goal_id: str):
        """Signal cooperative cancellation for an in-flight or pending goal."""
        self._cancelled_goals.add(goal_id)

    def is_cancelled(self, goal_id: str) -> bool:
        """Check whether cancellation was requested for a goal."""
        return goal_id in self._cancelled_goals

    def resume_goal(
        self,
        goal_id: str,
        observe_fn: Optional[Callable[[], Dict[str, Any]]] = None,
    ) -> GoalExecutionResult:
        """Resume an existing goal loaded from persistent SQLite storage."""
        plan = self.store.load_plan(goal_id)
        if not plan:
            return GoalExecutionResult(
                goal_id=goal_id,
                status=GoalStatus.FAILED,
                completed_steps=[],
                audit_trail=[{"error": f"Goal '{goal_id}' not found in checkpoint store"}],
            )
        return self.execute_plan(plan, observe_fn=observe_fn)

    def execute_plan(
        self,
        plan: ExecutionPlan,
        observe_fn: Optional[Callable[[], Dict[str, Any]]] = None,
    ) -> GoalExecutionResult:
        """Execute all steps in an ExecutionPlan respecting DAG dependencies and checkpoint rules."""
        with _DESKTOP_GOAL_LOCK:
            start_t = time.perf_counter()
            plan.status = GoalStatus.EXECUTING

            # 1. Validate DAG
            valid, err = plan.validate_dag()
            if not valid:
                plan.status = GoalStatus.FAILED
                elapsed_ms = (time.perf_counter() - start_t) * 1000.0
                return GoalExecutionResult(
                    goal_id=plan.goal_id,
                    status=GoalStatus.FAILED,
                    completed_steps=[],
                    failed_step=None,
                    wall_clock_ms=elapsed_ms,
                    audit_trail=[{"error": f"Invalid DAG plan: {err}"}],
                )

            # 2. Checkpoint recovery & crash check BEFORE saving:
            # If this goal was previously started, load persisted step states and check for stranded DISPATCHING actions
            if self.store.has_goal(plan.goal_id):
                # Synchronize in-memory plan with already completed steps to PREVENT REPLAY
                persisted_steps = self.store.get_plan_steps(plan.goal_id)
                for step in plan.steps:
                    if step.step_id in persisted_steps:
                        p_status = persisted_steps[step.step_id]["status"]
                        if p_status == "completed":
                            step.status = StepExecutionState.COMPLETED
                        elif p_status == "failed":
                            step.status = StepExecutionState.FAILED
                            step.error_message = persisted_steps[step.step_id].get("error_message")

                # Query any step stranded in DISPATCHING from an unexpected process kill or restart
                crashed_steps = self.store.get_crashed_steps(plan.goal_id)
                if crashed_steps:
                    logger.info("Found %d crashed step(s) in DISPATCHING; reconciling state", len(crashed_steps))
                    self._reconcile_crashed_steps(plan, crashed_steps, observe_fn=observe_fn)

            # 3. Persist plan to SQLite store (with preserve_existing_states=True)
            self.store.save_plan(plan, preserve_existing_states=True)

            # Initialize completed steps in plan order
            completed_step_ids: List[str] = [s.step_id for s in plan.steps if s.status == StepExecutionState.COMPLETED]
            audit_trail: List[Dict[str, Any]] = []

            # 4. Sequential execution loop
            while True:
                if self.is_cancelled(plan.goal_id):
                    logger.warning("Goal %s was cancelled by user; halting execution", plan.goal_id)
                    plan.status = GoalStatus.ABORTED
                    self.store.update_goal_status(plan.goal_id, GoalStatus.ABORTED)
                    elapsed_ms = (time.perf_counter() - start_t) * 1000.0
                    return GoalExecutionResult(
                        goal_id=plan.goal_id,
                        status=GoalStatus.ABORTED,
                        completed_steps=completed_step_ids,
                        wall_clock_ms=elapsed_ms,
                        audit_trail=audit_trail,
                    )

                step = plan.get_next_eligible_step()
                if not step:
                    # All steps completed or no more eligible steps
                    break

                step_intent = self._step_to_intent(step)

                # Protocol: Record durable DISPATCHING state BEFORE invoking hardware action
                self.store.record_pre_dispatch(plan.goal_id, step.step_id, step_intent.to_dict())

                # Execute step through ActionOrchestrator
                orch_result = self.orchestrator.execute_step(
                    step_intent,
                    observe_fn=observe_fn,
                )
                audit_trail.append({"step_id": step.step_id, "result": orch_result})

                # Record dispatch result in store
                self.store.record_dispatch_result(
                    plan.goal_id,
                    step.step_id,
                    orch_result.get("dispatch_result", {}),
                )

                # Record verification outcome in store
                verif_data = orch_result.get("verification", {})
                status_str = verif_data.get("status", "failed")
                self.store.record_verification(
                    plan.goal_id,
                    step.step_id,
                    status=status_str,
                    evidence_dict=verif_data,
                    recovery_dict=orch_result.get("recovery_decision"),
                )

                if orch_result.get("success", False):
                    step.status = StepExecutionState.COMPLETED
                    completed_step_ids.append(step.step_id)

                    # Persist durable checkpoint
                    self.store.save_checkpoint(
                        goal_id=plan.goal_id,
                        step_id=step.step_id,
                        active_window=verif_data.get("details", {}).get("active_window", ""),
                        observation_id=verif_data.get("details", {}).get("observation_id", ""),
                        completed_steps=completed_step_ids,
                    )
                else:
                    step.status = StepExecutionState.FAILED
                    step.error_message = verif_data.get("error_message", "Step failed verification")

                    # Step failed unrecoverably: trigger compensation pipeline
                    logger.warning("Step %s failed (%s); triggering compensatory rollback", step.step_id, step.error_message)
                    compensations_run, all_succeeded = self._rollback_compensations(plan, completed_step_ids, observe_fn=observe_fn)
                    if compensations_run and all_succeeded:
                        plan.status = GoalStatus.COMPENSATED
                    elif compensations_run and not all_succeeded:
                        plan.status = GoalStatus.COMPENSATION_FAILED
                    else:
                        plan.status = GoalStatus.FAILED
                    self.store.update_goal_status(plan.goal_id, plan.status)

                    elapsed_ms = (time.perf_counter() - start_t) * 1000.0
                    return GoalExecutionResult(
                        goal_id=plan.goal_id,
                        status=plan.status,
                        completed_steps=completed_step_ids,
                        failed_step=step.step_id,
                        compensations_executed=compensations_run,
                        wall_clock_ms=elapsed_ms,
                        audit_trail=audit_trail,
                    )

            # Check if all steps in plan actually completed
            all_completed = all(s.status == StepExecutionState.COMPLETED for s in plan.steps)
            if not all_completed:
                failed_step = next((s.step_id for s in plan.steps if s.status == StepExecutionState.FAILED), None)
                plan.status = GoalStatus.FAILED
                self.store.update_goal_status(plan.goal_id, GoalStatus.FAILED)
                elapsed_ms = (time.perf_counter() - start_t) * 1000.0
                return GoalExecutionResult(
                    goal_id=plan.goal_id,
                    status=GoalStatus.FAILED,
                    completed_steps=completed_step_ids,
                    failed_step=failed_step,
                    wall_clock_ms=elapsed_ms,
                    audit_trail=audit_trail,
                )

            # All steps successfully completed
            plan.status = GoalStatus.COMPLETED
            self.store.update_goal_status(plan.goal_id, GoalStatus.COMPLETED)
            elapsed_ms = (time.perf_counter() - start_t) * 1000.0
            return GoalExecutionResult(
                goal_id=plan.goal_id,
                status=GoalStatus.COMPLETED,
                completed_steps=completed_step_ids,
                wall_clock_ms=elapsed_ms,
                audit_trail=audit_trail,
            )

    def _step_to_intent(self, step: PlanStep) -> ActionIntent:
        """Convert a PlanStep into a typed ActionIntent with ActionExpectation."""
        exp = ActionExpectation(
            expected_window_title=step.expected_window_title,
            expected_text=step.expected_text,
            disallowed_text=step.disallowed_text,
            timeout_s=step.timeout_s,
            risk_level=ActionRiskLevel(step.risk_level) if step.risk_level in [e.value for e in ActionRiskLevel] else ActionRiskLevel.SAFE_REPEATABLE,
            is_sensitive=(step.risk_level == "sensitive"),
        )
        return ActionIntent(
            intent_id=f"{step.step_id}_{int(time.time()*1000)}",
            action_type=step.action_type,
            target_query=step.target_query,
            parameters=dict(step.parameters),
            expectation=exp,
            risk_level=exp.risk_level,
        )

    def _reconcile_crashed_steps(
        self,
        plan: ExecutionPlan,
        crashed_steps: List[Dict[str, Any]],
        observe_fn: Optional[Callable[[], Dict[str, Any]]] = None,
    ):
        """Reconcile crashed steps using fresh UI evidence before restarting execution."""
        fresh_obs = observe_fn() if observe_fn else None

        for item in crashed_steps:
            sid = item["step_id"]
            step = plan.get_step(sid)
            if not step:
                continue

            # Verify if expected postcondition is already visible on screen
            if fresh_obs and (step.expected_window_title or step.expected_text):
                matched = False
                if step.expected_window_title and step.expected_window_title.lower() in fresh_obs.get("active_window", "").lower():
                    matched = True
                if step.expected_text and step.expected_text.lower() in fresh_obs.get("text", "").lower():
                    matched = True

                if matched:
                    logger.info("Crashed step %s was already satisfied on screen; reconciling as COMPLETED", sid)
                    step.status = StepExecutionState.COMPLETED
                    self.store.record_verification(
                        plan.goal_id,
                        sid,
                        status="completed",
                        evidence_dict={"reconciled_after_crash": True},
                    )
                    continue

            # If not verified and action was non-idempotent: MUST NOT blindly resend
            if step.risk_level == "non_idempotent":
                logger.error("Crashed step %s is non-idempotent and unverified; marking FAILED for safety", sid)
                step.status = StepExecutionState.FAILED
                step.error_message = "Crashed in DISPATCHING for non-idempotent action; aborted for safety"
                self.store.record_verification(
                    plan.goal_id,
                    sid,
                    status="failed",
                    evidence_dict={"aborted_non_idempotent_crash": True},
                )
            else:
                # Safe repeatable action: reset to pending for clean retry
                logger.info("Crashed step %s is safe repeatable; resetting to PENDING for retry", sid)
                step.status = StepExecutionState.PENDING

    def _rollback_compensations(
        self,
        plan: ExecutionPlan,
        completed_step_ids: List[str],
        observe_fn: Optional[Callable[[], Dict[str, Any]]] = None,
    ) -> Tuple[List[str], bool]:
        """Execute compensations in reverse order for completed reversible steps.
        
        Returns (executed_step_ids, all_compensations_succeeded).
        """
        executed_compensations: List[str] = []
        all_succeeded = True
        plan.status = GoalStatus.COMPENSATING

        # Reverse chronological order
        for sid in reversed(completed_step_ids):
            step = plan.get_step(sid)
            if not step or not step.compensation or not step.compensation.is_reversible:
                continue

            comp = step.compensation
            logger.info("Executing compensation for step %s: %s (%s)", sid, comp.action_type, comp.description)

            comp_intent = ActionIntent(
                intent_id=f"comp_{sid}_{int(time.time()*1000)}",
                action_type=comp.action_type,
                parameters=dict(comp.parameters),
                risk_level=ActionRiskLevel.SAFE_REPEATABLE,
            )

            res = self.orchestrator.execute_step(comp_intent, observe_fn=observe_fn)
            comp.executed = True
            comp.success = res.get("success", False)
            if not comp.success:
                all_succeeded = False

            self.store.record_compensation(
                goal_id=plan.goal_id,
                step_id=sid,
                action_type=comp.action_type,
                action_dict=comp.to_dict(),
                status="compensated" if comp.success else "compensation_failed",
                result_dict=res,
            )
            executed_compensations.append(sid)

        return executed_compensations, all_succeeded
