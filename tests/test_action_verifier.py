"""Comprehensive unit tests for ActionVerifier and ActionRecoveryDecider.

Validates:
1. Rejection of blind API confirmations when postconditions are not satisfied.
2. Verification of window title, OCR text, and UIA element visibility.
3. Stale observation detection.
4. Strict safety boundaries: Max 1 retry for safe repeatable actions, ZERO retries for non-idempotent actions.
5. Sensitive data redaction (passwords, tokens).
6. Disallowed text error modal detection and recovery.
"""

import pytest
from action_expectations import (
    ActionExpectation,
    ActionIntent,
    ActionRiskLevel,
    ActionState,
)
from action_verifier import (
    ActionVerifier,
    VerificationStatus,
)
from action_recovery import (
    ActionRecoveryDecider,
    RecoveryStrategy,
)


@pytest.fixture
def verifier():
    return ActionVerifier()


@pytest.fixture
def recovery():
    return ActionRecoveryDecider(max_safe_retries=1)


def test_reject_blind_api_success_when_outcome_missing(verifier):
    """
    Critical requirement: A successful mouse API return value must NEVER
    be accepted as proof of action success if expected outcome is absent.
    """
    intent = ActionIntent(
        action_type="click_element",
        target_id=10,
        expectation=ActionExpectation(expected_window_title="Settings"),
        risk_level=ActionRiskLevel.SAFE_REPEATABLE,
    )
    pre_obs = {"observation_id": "obs_1", "active_window": "Chrome"}
    dispatch_result = {"success": True, "button": "left"}
    # Post observation shows active window is still Chrome, Settings did NOT open
    post_obs = {"observation_id": "obs_2", "active_window": "Chrome"}

    evidence = verifier.verify(intent, pre_obs, dispatch_result, post_obs)
    assert evidence.status == VerificationStatus.FAILED
    assert intent.state == ActionState.FAILED
    assert "Settings" in evidence.error_message


def test_window_title_verification_success(verifier):
    intent = ActionIntent(
        action_type="focus_window",
        target_query="Settings",
        expectation=ActionExpectation(expected_window_title="Settings"),
    )
    pre_obs = {"observation_id": "obs_1", "active_window": "Chrome"}
    dispatch_result = {"success": True}
    post_obs = {"observation_id": "obs_2", "active_window": "Windows Settings - System"}

    evidence = verifier.verify(intent, pre_obs, dispatch_result, post_obs)
    assert evidence.status == VerificationStatus.CONFIRMED
    assert intent.state == ActionState.CONFIRMED
    assert evidence.confidence >= 0.95


def test_expected_text_verification_success(verifier):
    intent = ActionIntent(
        action_type="type_text",
        parameters={"text": "hello"},
        expectation=ActionExpectation(expected_text="Search results for hello"),
    )
    pre_obs = {"observation_id": "obs_1"}
    dispatch_result = {"success": True}
    post_obs = {
        "observation_id": "obs_2",
        "text": "Header bar\nSearch results for hello\nPage 1 of 5",
        "elements": [],
    }

    evidence = verifier.verify(intent, pre_obs, dispatch_result, post_obs)
    assert evidence.status == VerificationStatus.CONFIRMED
    assert intent.state == ActionState.CONFIRMED


def test_stale_observation_detection(verifier):
    intent = ActionIntent(
        action_type="click_element",
        target_id=5,
        expectation=ActionExpectation(expected_text="Updated"),
    )
    pre_obs = {"observation_id": "identical_snapshot_123"}
    dispatch_result = {"success": True}
    # Passing the exact same observation as post_obs
    post_obs = {"observation_id": "identical_snapshot_123", "text": "Updated"}

    evidence = verifier.verify(intent, pre_obs, dispatch_result, post_obs)
    assert evidence.status == VerificationStatus.UNCERTAIN
    assert evidence.evidence_type == "stale_observation"


def test_disallowed_text_modal_error_detected(verifier, recovery):
    intent = ActionIntent(
        action_type="click_element",
        target_id=12,
        expectation=ActionExpectation(
            expected_text="Success",
            disallowed_text="Access Denied",
        ),
    )
    pre_obs = {"observation_id": "obs_1"}
    dispatch_result = {"success": True}
    post_obs = {"observation_id": "obs_2", "text": "Error: Access Denied to resource"}

    evidence = verifier.verify(intent, pre_obs, dispatch_result, post_obs)
    assert evidence.status == VerificationStatus.FAILED
    assert evidence.evidence_type == "disallowed_text_detected"

    # Recovery should decide to dismiss the modal dialog
    rec = recovery.decide(intent, evidence, pre_obs, post_obs)
    assert rec.strategy == RecoveryStrategy.DISMISS_MODAL
    assert rec.allowed is True


def test_non_idempotent_action_never_retried_automatically(recovery):
    """
    Critical safety requirement: Submitting payment, deleting files, or sending
    messages must NEVER be repeated automatically on failure.
    """
    intent = ActionIntent(
        action_type="click_element",
        target_query="Submit Payment",
        risk_level=ActionRiskLevel.NON_IDEMPOTENT,
    )
    evidence = verifier_failure_evidence = ActionVerifier().verify(
        intent,
        pre_obs={"observation_id": "obs_1"},
        dispatch_result={"success": True},
        post_obs={"observation_id": "obs_2", "text": "Processing..."},
    )
    decision = recovery.decide(intent, evidence)
    assert decision.strategy == RecoveryStrategy.ABORT_FOR_SAFETY
    assert decision.allowed is False
    assert "Refusing automatic retry for non-idempotent action" in decision.reason


def test_safe_repeatable_action_retry_limit(recovery):
    """Safe repeatable action can be retried at most once."""
    intent = ActionIntent(
        intent_id="intent_tab_switch",
        action_type="click_element",
        target_query="Tab 2",
        risk_level=ActionRiskLevel.SAFE_REPEATABLE,
    )
    from action_verifier import VerificationEvidence
    evidence = VerificationEvidence(
        status=VerificationStatus.FAILED,
        confidence=0.9,
        evidence_type="window_title_mismatch",
        error_message="Tab did not switch",
    )

    # First retry: Allowed
    rec1 = recovery.decide(intent, evidence)
    assert rec1.strategy == RecoveryStrategy.RETRY_SAFE
    assert rec1.allowed is True
    assert rec1.retry_count == 1

    # Second retry: Rejected
    rec2 = recovery.decide(intent, evidence)
    assert rec2.strategy == RecoveryStrategy.MARK_UNCERTAIN
    assert rec2.allowed is False


def test_sensitive_field_redaction():
    """Ensure passwords and secrets are never logged or leaked in string serialization."""
    intent = ActionIntent(
        action_type="type_text",
        parameters={"text": "super_secret_password_123", "profile": "natural"},
        is_sensitive=True,
    )
    sanitized = intent.sanitized_parameters()
    assert sanitized["text"] == "***REDACTED***"
    as_dict = intent.to_dict()
    assert as_dict["parameters"]["text"] == "***REDACTED***"
