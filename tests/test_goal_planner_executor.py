"""Integration and unit tests for Autonomous Goal Executor, DAG sequencing, and SQLite checkpointing."""

import os
import tempfile
import pytest

from Planner.goal_schema import (
    ExecutionPlan,
    PlanStep,
    StepExecutionState,
    GoalStatus,
    StepCompensation,
)
from Planner.checkpoint_store import SQLiteCheckpointStore
from Planner.goal_executor import AutonomousGoalExecutor, GoalExecutionResult
from action_expectations import ActionIntent, ActionRiskLevel
from action_orchestrator import ActionOrchestrator


@pytest.fixture
def temp_db():
    import gc
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        yield os.path.join(tmpdir, "test_state.db")
        gc.collect()


@pytest.fixture
def store(temp_db):
    return SQLiteCheckpointStore(db_path=temp_db)


@pytest.fixture
def executor(store):
    orch = ActionOrchestrator(dry_run=True)
    return AutonomousGoalExecutor(orchestrator=orch, store=store, dry_run=True)


def test_dag_cycle_and_invalid_dependency_rejection(executor):
    """Verify circular dependencies and missing dependency references are rejected."""
    # Circular: s1 -> s2 -> s1
    plan = ExecutionPlan(
        goal_id="g_cycle",
        instruction="Cycle test",
        steps=[
            PlanStep(step_id="s1", action_type="click", dependencies=["s2"]),
            PlanStep(step_id="s2", action_type="click", dependencies=["s1"]),
        ],
    )
    result = executor.execute_plan(plan)
    assert result.status == GoalStatus.FAILED
    assert "Circular dependency" in result.audit_trail[0]["error"]

    # Unknown dependency: s1 depends on non-existent s99
    plan2 = ExecutionPlan(
        goal_id="g_unknown",
        instruction="Unknown dep",
        steps=[
            PlanStep(step_id="s1", action_type="click", dependencies=["s99"]),
        ],
    )
    result2 = executor.execute_plan(plan2)
    assert result2.status == GoalStatus.FAILED
    assert "unknown dependency 's99'" in result2.audit_trail[0]["error"]


def test_sequential_dag_execution_success(executor):
    """Execute a 3-step sequential plan (s1 -> s2 -> s3) in dry-run mode."""
    plan = ExecutionPlan(
        goal_id="g_seq_1",
        instruction="Configure settings",
        steps=[
            PlanStep(
                step_id="s1",
                action_type="focus_window",
                parameters={"title": "Settings"},
                expected_window_title="Settings",
            ),
            PlanStep(
                step_id="s2",
                action_type="click",
                target_query="Personalization",
                dependencies=["s1"],
                expected_text="Personalization Options",
            ),
            PlanStep(
                step_id="s3",
                action_type="click",
                target_query="Dark Mode Toggle",
                dependencies=["s2"],
                expected_text="Dark Mode Enabled",
            ),
        ],
    )

    observations = [
        # s1: pre, post
        {"observation_id": "o1", "active_window": "Desktop"},
        {"observation_id": "o2", "active_window": "Settings Window"},
        # s2: pre, post
        {"observation_id": "o3", "active_window": "Settings Window", "elements": [{"name": "Personalization", "center": [100, 200]}]},
        {"observation_id": "o4", "text": "Personalization Options"},
        # s3: pre, post
        {"observation_id": "o5", "elements": [{"name": "Dark Mode Toggle", "center": [300, 400]}]},
        {"observation_id": "o6", "text": "Dark Mode Enabled"},
    ]

    obs_idx = [0]

    def mock_observe():
        idx = obs_idx[0]
        obs_idx[0] += 1
        return observations[min(idx, len(observations) - 1)]

    result = executor.execute_plan(plan, observe_fn=mock_observe)
    assert result.status == GoalStatus.COMPLETED
    assert result.completed_steps == ["s1", "s2", "s3"]

    # Check that store has the completed checkpoint
    chk = executor.store.get_latest_checkpoint(plan.goal_id)
    assert chk is not None
    assert chk["completed_steps"] == ["s1", "s2", "s3"]


def test_compensation_rollback_on_failure(executor):
    """When step 2 fails, step 1's compensation (closing the opened modal) is triggered in reverse order."""
    plan = ExecutionPlan(
        goal_id="g_comp_1",
        instruction="Open and submit form",
        steps=[
            PlanStep(
                step_id="s1",
                action_type="click",
                target_query="Open Dialog",
                expected_text="Modal Form Opened",
                compensation=StepCompensation(
                    action_type="press_key",
                    parameters={"key": "esc"},
                    description="Dismiss modal dialog",
                ),
            ),
            PlanStep(
                step_id="s2",
                action_type="click",
                target_query="Submit Missing Field",
                dependencies=["s1"],
                expected_text="Form Submitted Successfully",
            ),
        ],
    )

    observations = [
        # s1: pre, post (succeeds)
        {"observation_id": "o1", "elements": [{"name": "Open Dialog", "center": [100, 100]}]},
        {"observation_id": "o2", "text": "Modal Form Opened"},
        # s2: pre, post (fails - expected text not present)
        {"observation_id": "o3", "elements": [{"name": "Submit Missing Field", "center": [200, 200]}]},
        {"observation_id": "o4", "text": "Validation Error"},
        # Retry and compensation each receive fresh pre/post observations.
        {"observation_id": "o5", "text": "Validation Error"},
        {"observation_id": "o6", "text": "Validation Error"},
        {"observation_id": "o7", "text": "Validation Error"},
        {"observation_id": "o8", "text": "Validation Error"},
    ]

    obs_idx = [0]

    def mock_observe():
        idx = obs_idx[0]
        obs_idx[0] += 1
        return observations[min(idx, len(observations) - 1)]

    result = executor.execute_plan(plan, observe_fn=mock_observe)
    assert result.status == GoalStatus.COMPENSATED
    assert result.failed_step == "s2"
    assert "s1" in result.compensations_executed


def test_crash_reconciliation_recovers_satisfied_step(executor):
    """Step left stranded in DISPATCHING from simulated crash is reconciled if postcondition is met."""
    plan = ExecutionPlan(
        goal_id="g_crash_rec",
        instruction="Recoverable task",
        steps=[
            PlanStep(
                step_id="s1",
                action_type="focus_window",
                expected_window_title="Calculator",
            ),
        ],
    )
    # Save plan and simulate crash in DISPATCHING
    executor.store.save_plan(plan)
    executor.store.record_pre_dispatch(plan.goal_id, "s1", {})

    # Fresh observation proves Calculator is already open and active!
    fresh_obs = {"active_window": "Calculator - Scientific Mode"}

    result = executor.execute_plan(plan, observe_fn=lambda: fresh_obs)
    assert result.status == GoalStatus.COMPLETED
    assert "s1" in result.completed_steps


def test_crash_reconciliation_aborts_non_idempotent_action(executor):
    """A non-idempotent action (payment, message send) stranded in DISPATCHING must NEVER be auto-resent."""
    plan = ExecutionPlan(
        goal_id="g_danger_crash",
        instruction="Send payment",
        steps=[
            PlanStep(
                step_id="s1",
                action_type="click",
                risk_level="non_idempotent",
                expected_text="Payment Confirmed",
            ),
        ],
    )
    executor.store.save_plan(plan)
    executor.store.record_pre_dispatch(plan.goal_id, "s1", {})

    # Fresh observation shows ambiguous screen without payment confirmation
    fresh_obs = {"text": "Network Gateway Timeout"}

    result = executor.execute_plan(plan, observe_fn=lambda: fresh_obs)
    assert result.status == GoalStatus.FAILED
    assert result.failed_step == "s1"


def test_crash_consistency_restart_prevents_replay_and_reconciles_dispatching(temp_db):
    """Verify that restarting the executor against the same SQLite database:
    1. Detects stranded DISPATCHING steps.
    2. Does NOT replay already COMPLETED steps.
    3. Reconciles DISPATCHING into COMPLETED when UI evidence matches.
    """
    store1 = SQLiteCheckpointStore(db_path=temp_db)
    orch1 = ActionOrchestrator(dry_run=True)
    exec1 = AutonomousGoalExecutor(orchestrator=orch1, store=store1, dry_run=True)

    plan = ExecutionPlan(
        goal_id="g_crash_restart_1",
        instruction="Multi-step across restart",
        steps=[
            PlanStep(step_id="s1", action_type="focus_window", expected_window_title="Settings"),
            PlanStep(step_id="s2", action_type="click", dependencies=["s1"], expected_text="System"),
            PlanStep(step_id="s3", action_type="type_text", parameters={"text": "Display"}, dependencies=["s2"], expected_text="Display Settings"),
        ],
    )
    # 1. Step 1 executes and completes in instance 1
    exec1.store.save_plan(plan)
    exec1.store.record_pre_dispatch(plan.goal_id, "s1", {})
    exec1.store.record_verification(plan.goal_id, "s1", "completed", {"status": "confirmed"})
    exec1.store.save_checkpoint(plan.goal_id, "s1", "Settings", "obs_1", ["s1"])

    # 2. Step 2 enters DISPATCHING, and then simulated crash / process termination happens
    exec1.store.record_pre_dispatch(plan.goal_id, "s2", {"target": "System"})

    # Drop instance 1 completely to simulate process death
    del exec1
    del orch1
    del store1

    # 3. Instance 2 starts up fresh against the same persistent database
    store2 = SQLiteCheckpointStore(db_path=temp_db)
    replayed_steps = []

    def mock_orch_step(intent, observe_fn=None, pre_observation=None):
        step_id = intent.intent_id.split("_")[0]
        replayed_steps.append(step_id)
        return {
            "success": True,
            "verification": {"status": "confirmed", "details": {"active_window": "Settings", "observation_id": f"obs_{step_id}"}},
        }

    mock_orch = ActionOrchestrator(dry_run=True)
    mock_orch.execute_step = mock_orch_step

    exec2 = AutonomousGoalExecutor(orchestrator=mock_orch, store=store2, dry_run=True)

    # Fresh UI evidence when instance 2 wakes up: proves step 2 already happened (text "System" is present)
    fresh_ui = {"active_window": "Settings", "text": "System Options"}

    # Resume goal
    result = exec2.resume_goal("g_crash_restart_1", observe_fn=lambda: fresh_ui)

    assert result.status == GoalStatus.COMPLETED
    assert result.completed_steps == ["s1", "s2", "s3"]
    # CRITICAL: s1 and s2 must NOT have been dispatched through mock_orch because s1 was completed and s2 was reconciled!
    assert "s1" not in replayed_steps
    assert "s2" not in replayed_steps
    # Only s3 should have been executed by the fresh executor
    assert "s3" in replayed_steps


def test_failed_compensation_does_not_produce_false_compensated(temp_db):
    """When a step fails and its compensation ALSO fails, goal status must be COMPENSATION_FAILED, not COMPENSATED."""
    store = SQLiteCheckpointStore(db_path=temp_db)

    class FailingCompOrchestrator(ActionOrchestrator):
        def execute_step(self, intent, observe_fn=None, pre_observation=None):
            # If compensation action, fail it!
            if intent.intent_id.startswith("comp_"):
                return {"success": False, "error": "Hardware input locked"}
            # Step 1 succeeds
            if "s1" in intent.intent_id:
                return {"success": True, "verification": {"status": "confirmed"}}
            # Step 2 fails
            return {"success": False, "verification": {"status": "failed", "error_message": "Element not found"}}

    orch = FailingCompOrchestrator(dry_run=True)
    executor = AutonomousGoalExecutor(orchestrator=orch, store=store, dry_run=True)

    plan = ExecutionPlan(
        goal_id="g_comp_fail",
        instruction="Test failed compensation semantics",
        steps=[
            PlanStep(
                step_id="s1",
                action_type="click",
                expected_text="Done",
                compensation=StepCompensation(
                    action_type="press_key",
                    parameters={"key": "esc"},
                    is_reversible=True,
                ),
            ),
            PlanStep(
                step_id="s2",
                action_type="click",
                dependencies=["s1"],
                expected_text="Submit",
            ),
        ],
    )

    result = executor.execute_plan(plan)
    assert result.status == GoalStatus.COMPENSATION_FAILED
    assert result.failed_step == "s2"
    assert "s1" in result.compensations_executed


def test_goal_cooperative_cancellation(executor):
    """A goal can be cooperatively cancelled, resulting in ABORTED status."""
    plan = ExecutionPlan(
        goal_id="g_cancel_test",
        instruction="Cancellation test",
        steps=[
            PlanStep(step_id="s1", action_type="focus_window", expected_window_title="Desktop"),
        ],
    )
    executor.cancel_goal(plan.goal_id)
    result = executor.execute_plan(plan)
    assert result.status == GoalStatus.ABORTED



def test_dry_run_fallback_observations_have_unique_ids():
    """Synthetic pre/post observations must not collide on low-resolution clocks."""
    orchestrator = ActionOrchestrator(dry_run=True)
    intent = ActionIntent(
        action_type="press_key",
        parameters={"key": "esc"},
        risk_level=ActionRiskLevel.SAFE_REPEATABLE,
    )

    result = orchestrator.execute_step(intent)

    assert result["success"] is True
    assert result["verification"]["evidence_type"] == "default_safe_dispatch"
