"""Unit tests for the Human-Like Planner Layer, Verification Tiers, Recovery Provenance, and Resumability."""

import os
import tempfile
import pytest
from unittest.mock import MagicMock, patch

from Planner import (
    ActionRiskLevel,
    Checkpoint,
    HumanLikePlanner,
    Plan,
    PlanStep,
    RecoveryProvenanceRecord,
    StepActionType,
    StepStatus,
    VerificationLevel,
)


def test_plan_goal_decomposition_hackthebox():
    planner = HumanLikePlanner()
    plan = planner.plan_goal("open chrome and navigate to Hack the box website")

    assert isinstance(plan, Plan)
    assert len(plan.steps) >= 7
    assert plan.goal == "open chrome and navigate to Hack the box website"

    # Step 1: Open Start search
    s1 = plan.steps[0]
    assert s1.action_type == StepActionType.HOTKEY
    assert s1.parameters.get("keys") == ["win"]
    assert s1.risk_level == ActionRiskLevel.IDEMPOTENT
    assert s1.verification_level == VerificationLevel.DIRECT_STATE

    # Step 2: Type chrome
    s2 = plan.steps[1]
    assert s2.action_type == StepActionType.TYPE_TEXT
    assert s2.parameters.get("text") == "chrome"

    # Step 3: Press Enter
    s3 = plan.steps[2]
    assert s3.action_type == StepActionType.PRESS_KEY
    assert s3.parameters.get("key") == "enter"

    # Destination URL step
    nav_step = None
    for s in plan.steps:
        if "hackthebox" in str(s.parameters.get("text", "")).lower():
            nav_step = s
            break
    assert nav_step is not None
    assert nav_step.action_type == StepActionType.TYPE_TEXT
    assert nav_step.risk_level == ActionRiskLevel.CONSEQUENTIAL


def test_plan_goal_decomposition_brave_youtube():
    planner = HumanLikePlanner()
    plan = planner.plan_goal("open brave and search for youtube")

    assert any(s.parameters.get("text") == "brave" for s in plan.steps)
    assert any("youtube" in str(s.parameters.get("text", "")) for s in plan.steps)


def test_plan_step_burst_time_and_provenance_tracking():
    mock_controller = MagicMock()
    mock_controller.task.return_value.__enter__.return_value = mock_controller
    mock_controller.task.return_value.__exit__.return_value = None
    mock_controller.windows.return_value = {"active_window": "Test App", "windows": []}

    planner = HumanLikePlanner(controller=mock_controller)
    plan = Plan(goal="test type text")
    step = plan.add_step(
        intent="Type hello",
        action_type=StepActionType.TYPE_TEXT,
        parameters={"text": "hello"},
    )

    success = planner.execute_step(step, plan, controller=mock_controller)
    assert success is True
    assert step.status == StepStatus.COMPLETED
    assert step.burst_time_ms >= 0.0
    assert len(plan.provenance_log) == 1

    rec = plan.provenance_log[0]
    assert rec.step_number == 1
    assert rec.attempt_id == 1
    assert rec.post_condition_satisfied is True
    assert rec.action_type == "type_text"
    mock_controller.type_text.assert_called_once_with("hello", profile="natural")


def test_micro_recovery_retry_on_failure():
    mock_controller = MagicMock()
    mock_controller.task.return_value.__enter__.return_value = mock_controller
    mock_controller.task.return_value.__exit__.return_value = None
    mock_controller.windows.return_value = {"active_window": "Wrong Window", "windows": []}
    mock_controller.observe.return_value = {"elements": [], "active_window": "Wrong Window"}

    planner = HumanLikePlanner(controller=mock_controller)
    plan = Plan(goal="test verify")
    step = plan.add_step(
        intent="Verify target window",
        action_type=StepActionType.VERIFY,
        parameters={"expected": ["Target Expected Window"], "timeout_s": 0.1},
        retry_budget=1,
    )

    success = planner.execute_step(step, plan, controller=mock_controller)
    assert success is False
    assert step.status == StepStatus.FAILED
    assert len(plan.provenance_log) == 2  # 1 initial + 1 retry
    assert plan.provenance_log[0].recovery_strategy == "micro_retry"
    mock_controller.press_key.assert_called_with("esc")


def test_checkpoint_persistence_and_resumption():
    with tempfile.TemporaryDirectory() as temp_dir:
        mock_controller = MagicMock()
        mock_controller.task.return_value.__enter__.return_value = mock_controller
        mock_controller.task.return_value.__exit__.return_value = None
        mock_controller.windows.return_value = {"active_window": "Google Chrome", "windows": []}

        planner = HumanLikePlanner(controller=mock_controller, checkpoint_dir=temp_dir)
        plan = Plan(goal="resumable workflow")
        plan.add_step("Step 1", StepActionType.HOTKEY, {"keys": ["win"]})
        plan.add_step("Step 2", StepActionType.PRESS_KEY, {"key": "enter"})

        # Execute first step and save checkpoint
        planner.execute_step(plan.steps[0], plan, controller=mock_controller)
        cp_file = plan.save_checkpoint(directory=temp_dir, active_window="Google Chrome")

        assert os.path.exists(cp_file)

        # Resume from checkpoint
        resumed_plan = Plan.load_checkpoint(cp_file)
        assert resumed_plan.goal == "resumable workflow"
        assert len(resumed_plan.steps) == 2
        assert resumed_plan.steps[0].status == StepStatus.COMPLETED
        assert resumed_plan.steps[1].status == StepStatus.PENDING

        # Finish execution via resume_plan
        finished_plan = planner.resume_plan(cp_file, controller=mock_controller)
        assert finished_plan.steps[1].status == StepStatus.COMPLETED


def test_execute_plan_with_callbacks():
    mock_controller = MagicMock()
    mock_controller.task.return_value.__enter__.return_value = mock_controller
    mock_controller.task.return_value.__exit__.return_value = None
    mock_controller.windows.return_value = {"active_window": "Chrome", "windows": []}

    planner = HumanLikePlanner(controller=mock_controller)
    plan = Plan(goal="test goal")
    plan.add_step(
        intent="Step 1 intent",
        action_type=StepActionType.HOTKEY,
        parameters={"keys": ["win"]},
    )

    callback_events = []

    def on_step(step, stage):
        callback_events.append((step.step_number, stage, step.intent))

    executed_plan = planner.execute_plan(plan, controller=mock_controller, on_step=on_step, save_checkpoints=False)

    assert executed_plan.completed is True
    assert executed_plan.total_burst_time_ms >= 0.0
    assert len(callback_events) == 2
    assert callback_events[0] == (1, "before", "Step 1 intent")
    assert callback_events[1] == (1, "after", "Step 1 intent")


if __name__ == "__main__":
    pytest.main([__file__])
