"""Unit tests for the Human-Like Planner Layer."""

import pytest
from unittest.mock import MagicMock, patch

from Planner import HumanLikePlanner, Plan, PlanStep, StepActionType, StepStatus


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
    assert "start" in s1.intent.lower() or "win" in s1.parameters.get("keys", [])

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


def test_plan_goal_decomposition_brave_youtube():
    planner = HumanLikePlanner()
    plan = planner.plan_goal("open brave and search for youtube")

    assert any(s.parameters.get("text") == "brave" for s in plan.steps)
    assert any("youtube" in str(s.parameters.get("text", "")) for s in plan.steps)


def test_plan_step_burst_time_tracking():
    mock_controller = MagicMock()
    mock_controller.task.return_value.__enter__.return_value = mock_controller
    mock_controller.task.return_value.__exit__.return_value = None

    planner = HumanLikePlanner(controller=mock_controller)
    step = PlanStep(
        step_number=1,
        intent="Type hello",
        action_type=StepActionType.TYPE_TEXT,
        parameters={"text": "hello"},
    )

    success = planner.execute_step(step, controller=mock_controller)
    assert success is True
    assert step.status == StepStatus.COMPLETED
    assert step.burst_time_ms >= 0.0
    mock_controller.type_text.assert_called_once_with("hello", profile="natural")


def test_execute_plan_with_callbacks():
    mock_controller = MagicMock()
    mock_controller.task.return_value.__enter__.return_value = mock_controller
    mock_controller.task.return_value.__exit__.return_value = None

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

    executed_plan = planner.execute_plan(plan, controller=mock_controller, on_step=on_step)

    assert executed_plan.completed is True
    assert executed_plan.total_burst_time_ms >= 0.0
    assert len(callback_events) == 2
    assert callback_events[0] == (1, "before", "Step 1 intent")
    assert callback_events[1] == (1, "after", "Step 1 intent")


if __name__ == "__main__":
    pytest.main([__file__])
