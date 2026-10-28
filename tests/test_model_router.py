"""Unit tests for multi-model routing configuration."""

import pytest
from config.models import ModelProfile, ModelRouter, TaskType, get_model_router


def test_default_model_router_initialization():
    router = get_model_router()
    assert router is not None

    # Check grounding uses local rules
    grounding_prof = router.get_profile(TaskType.GROUNDING)
    assert grounding_prof.provider == "local_rule"
    assert router.is_local_only(TaskType.GROUNDING) is True

    # Check state verification uses local rules
    verif_prof = router.get_profile(TaskType.STATE_VERIFICATION)
    assert verif_prof.provider == "local_rule"
    assert router.is_local_only(TaskType.STATE_VERIFICATION) is True

    # Check heavy reasoning tasks use reasoning tier
    decomp_prof = router.get_profile(TaskType.GOAL_DECOMPOSITION)
    assert decomp_prof.provider in {"google", "anthropic", "openai"}
    assert decomp_prof.max_tokens >= 1000


def test_custom_profile_override():
    router = ModelRouter()
    custom_prof = ModelProfile(
        provider="ollama",
        model_name="gemma:4b",
        max_tokens=300,
        temperature=0.1,
    )
    router.set_profile(TaskType.ACTION_PLANNING, custom_prof)

    retrieved = router.get_profile(TaskType.ACTION_PLANNING)
    assert retrieved.model_name == "gemma:4b"
    assert retrieved.provider == "ollama"
    assert router.is_local_only(TaskType.ACTION_PLANNING) is True


def test_model_router_summary():
    router = ModelRouter()
    summary = router.summary()

    assert TaskType.GROUNDING.value in summary
    assert TaskType.ACTION_PLANNING.value in summary
    assert TaskType.GOAL_DECOMPOSITION.value in summary
    assert summary[TaskType.GROUNDING.value]["provider"] == "local_rule"

