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
