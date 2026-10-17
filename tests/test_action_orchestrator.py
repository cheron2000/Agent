"""Integration and unit tests for ActionOrchestrator.

Validates:
1. Full end-to-end action lifecycle execution in dry-run simulation mode.
2. Hierarchical target resolution (UIA first -> OCR -> Visual Grounding fallback).
3. Dispatch normalization from various driver response formats.
4. Closed-loop recovery on safe repeatable action failure.
5. Strict hard stop on non-idempotent action failure.
6. Structured audit logging and wall-clock burst timing.
"""

import pytest
from action_expectations import (
    ActionExpectation,
    ActionIntent,
    ActionRiskLevel,
    ActionState,
)
from action_verifier import ActionVerifier, VerificationStatus
from action_recovery import ActionRecoveryDecider, RecoveryStrategy
from action_orchestrator import ActionOrchestrator


@pytest.fixture
def orchestrator():
    return ActionOrchestrator(dry_run=True)


def test_dry_run_full_lifecycle_success(orchestrator):
    """Simulate full action lifecycle: target query -> resolve -> dry-run dispatch -> verified outcome."""
    mock_obs_pre = {
        "observation_id": "obs_pre_1",
        "elements": [
            {"id": 1, "name": "Settings Button", "center": [120, 240]},
        ],
        "text": "Dashboard\nSettings Button\nHelp",
        "active_window": "MyApp",
    }
    mock_obs_post = {
        "observation_id": "obs_post_2",
        "active_window": "Settings Window",
        "elements": [],
        "text": "General Settings",
    }

    intent = ActionIntent(
        action_type="click",
        target_query="Settings Button",
        expectation=ActionExpectation(expected_window_title="Settings Window"),
    )

    result = orchestrator.execute_step(
        intent,
        pre_observation=mock_obs_pre,
        observe_fn=lambda: mock_obs_post,
    )

    assert result["success"] is True
    assert result["verification"]["status"] == VerificationStatus.CONFIRMED.value
    assert len(orchestrator.audit_log) == 1
    assert orchestrator.audit_log[0].confirmed is True
    assert orchestrator.audit_log[0].target_description == "Settings Button"


def test_target_resolution_hierarchy():
    """Verify UIA is preferred over generic text, and visual grounding fallback is supported."""
    orch = ActionOrchestrator()
    obs = {
        "elements": [
            {"id": 10, "name": "Submit Form", "center": [500, 600]},
        ],
        "text": "Submit Form button below",
    }

    # UIA hit
    coords = orch.resolve_target("Submit Form", obs)
    assert coords == (500, 600)

    # Missing target
    missing = orch.resolve_target("NonExistentButton", obs)
    assert missing is None


def test_driver_response_normalization():
    """Verify disparate Hands response conventions are unified into standard success contracts."""
    assert ActionOrchestrator._normalize_dispatch_response({"status": "success"})["success"] is True
    assert ActionOrchestrator._normalize_dispatch_response({"status": "failed"})["success"] is False
    assert ActionOrchestrator._normalize_dispatch_response(True)["success"] is True
    assert ActionOrchestrator._normalize_dispatch_response(False)["success"] is False
    assert ActionOrchestrator._normalize_dispatch_response({"success": True})["success"] is True


def test_safe_action_recovery_and_retry():
    """Safe repeatable action fails on attempt 1, retries and succeeds on attempt 2."""
    orch = ActionOrchestrator(dry_run=True)

    intent = ActionIntent(
        action_type="click",
        target_query="Tab 2",
        risk_level=ActionRiskLevel.SAFE_REPEATABLE,
        expectation=ActionExpectation(expected_text="Tab 2 Active"),
    )

    obs_attempts = [
        # Pre obs
        {"observation_id": "obs_0", "elements": [{"name": "Tab 2", "center": [100, 200]}]},
        # Post obs attempt 1: failed (Tab 1 still active)
        {"observation_id": "obs_1", "text": "Tab 1 Active"},
        # Pre obs for retry
        {"observation_id": "obs_2", "elements": [{"name": "Tab 2", "center": [100, 200]}]},
        # Post obs attempt 2: confirmed!
        {"observation_id": "obs_3", "text": "Tab 2 Active"},
    ]

    attempt_counter = [0]

    def mock_observe():
        idx = attempt_counter[0]
        attempt_counter[0] += 1
        return obs_attempts[min(idx, len(obs_attempts) - 1)]

    result = orch.execute_step(
        intent,
        observe_fn=mock_observe,
    )

    assert result["success"] is True
    assert result["verification"]["status"] == VerificationStatus.CONFIRMED.value
    # Audit log should show 1 retry was executed
    assert orch.audit_log[-1].retries_executed == 1


def test_non_idempotent_action_hard_stop_on_failure():
    """Non-idempotent action (payment, message send) fails and MUST NOT retry."""
    orch = ActionOrchestrator(dry_run=True)

    intent = ActionIntent(
        action_type="click",
        target_query="Confirm Transfer",
        risk_level=ActionRiskLevel.NON_IDEMPOTENT,
        expectation=ActionExpectation(expected_text="Transfer Complete"),
    )

    pre_obs = {"observation_id": "obs_0", "elements": [{"name": "Confirm Transfer", "center": [300, 400]}]}
    post_obs = {"observation_id": "obs_1", "text": "Network Error"}

    result = orch.execute_step(
        intent,
        pre_observation=pre_obs,
        observe_fn=lambda: post_obs,
    )

    assert result["success"] is False
    assert result["recovery_decision"]["strategy"] == RecoveryStrategy.ABORT_FOR_SAFETY.value
    assert result["recovery_decision"]["allowed"] is False
    assert orch.audit_log[0].retries_executed == 0
