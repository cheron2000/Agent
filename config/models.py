"""Multi-Model Routing and Configuration Engine.

Routes different cognitive and perception tasks to appropriately-sized models:
- Rule / Local OCR: Grounding, element resolving, simple state verification (0 latency, 0 cost).
- Fast / Lightweight (e.g., Gemini 2.0 Flash-Lite, Gemma-3-4B, GPT-4o-mini):
    Context analysis, screen state classification, rapid visual description.
- Balanced / Mid-tier (e.g., Gemini 2.0 Flash, Claude 3.5 Haiku):
    Action planning, step recovery reasoning, intent extraction.
- Reasoning / Heavy (e.g., Gemini 2.5 Pro, Claude 3.5 Sonnet / Opus):
    Complex DAG goal decomposition, failure root-cause analysis, long-horizon planning.
"""

from dataclasses import dataclass, field
from enum import Enum
import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger("config.models")


class TaskType(str, Enum):
    """Categorization of agent tasks by cognitive complexity."""
    GROUNDING = "grounding"                    # UI element detection, coordinate mapping (Rule/OCR/CV)
    STATE_VERIFICATION = "state_verification"  # Post-action sanity check (UIA/fast title/diff)
    CONTEXT_ANALYSIS = "context_analysis"      # Situational assessment, tab state, modal detection
    VISUAL_DESCRIPTION = "visual_description"  # General screen description, icon parsing
    ACTION_PLANNING = "action_planning"        # Single/next-step decision from observation
    GOAL_DECOMPOSITION = "goal_decomposition"  # Multi-step DAG generation, complex workflows
    FAILURE_RECOVERY = "failure_recovery"      # Deep diagnostic and compensatory rollback planning


@dataclass
class ModelProfile:
    """Configuration for a specific model tier."""
    provider: str                   # "google", "ollama", "openai", "anthropic", "local_rule"
    model_name: str                 # e.g., "gemini-2.0-flash-lite", "llava:7b", "gpt-4o-mini"
    max_tokens: int = 500
    temperature: float = 0.2
    timeout_s: float = 10.0
    fallback: Optional[str] = None  # Fallback model profile key
    extra_headers: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "provider": self.provider,
            "model_name": self.model_name,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "timeout_s": self.timeout_s,
            "fallback": self.fallback,
        }


# ── Default Task-to-Model Routing Table ──────────────────────────────────────
# Prioritizes speed and low latency for tight loops; reserves heavy models for planning.
DEFAULT_TASK_ROUTING: Dict[TaskType, ModelProfile] = {
    TaskType.GROUNDING: ModelProfile(
        provider="local_rule",
        model_name="uia_ocr_cv_hybrid",
        max_tokens=0,
        timeout_s=1.0,
    ),
    TaskType.STATE_VERIFICATION: ModelProfile(
        provider="local_rule",
        model_name="diff_and_uia_fast",
        max_tokens=0,
        timeout_s=1.5,
        fallback="fast_multimodal",
    ),
    TaskType.CONTEXT_ANALYSIS: ModelProfile(
        provider=os.getenv("CONTEXT_MODEL_PROVIDER", "google"),
        model_name=os.getenv("CONTEXT_MODEL", "gemini-2.0-flash-lite"),
        max_tokens=250,
        temperature=0.1,
        timeout_s=4.0,
        fallback="local_rules",
    ),
    TaskType.VISUAL_DESCRIPTION: ModelProfile(
        provider=os.getenv("VISION_MODEL_PROVIDER", "ollama"),
        model_name=os.getenv("VISION_MODEL", "llava:7b"),
        max_tokens=500,
        temperature=0.2,
        timeout_s=15.0,
        fallback="cloud_vision_fast",
    ),
    TaskType.ACTION_PLANNING: ModelProfile(
        provider=os.getenv("PLANNING_MODEL_PROVIDER", "google"),
        model_name=os.getenv("PLANNING_MODEL", "gemini-2.0-flash"),
        max_tokens=800,
        temperature=0.2,
        timeout_s=8.0,
    ),
    TaskType.GOAL_DECOMPOSITION: ModelProfile(
        provider=os.getenv("REASONING_MODEL_PROVIDER", "google"),
        model_name=os.getenv("REASONING_MODEL", "gemini-2.5-pro"),
        max_tokens=2500,
        temperature=0.3,
        timeout_s=25.0,
    ),
    TaskType.FAILURE_RECOVERY: ModelProfile(
        provider=os.getenv("RECOVERY_MODEL_PROVIDER", "google"),
        model_name=os.getenv("RECOVERY_MODEL", "gemini-2.5-pro"),
        max_tokens=1500,
        temperature=0.2,
        timeout_s=15.0,
    ),
}


class ModelRouter:
    """Selects and provides execution specs for models based on task requirements."""

    def __init__(self, custom_routing: Optional[Dict[TaskType, ModelProfile]] = None):
        self._routing = dict(DEFAULT_TASK_ROUTING)
        if custom_routing:
            self._routing.update(custom_routing)

    def get_profile(self, task: TaskType) -> ModelProfile:
        """Retrieve model configuration for a given task type."""
        return self._routing.get(task, self._routing[TaskType.CONTEXT_ANALYSIS])

    def set_profile(self, task: TaskType, profile: ModelProfile) -> None:
        """Dynamically override profile for a specific task."""
        self._routing[task] = profile

    def is_local_only(self, task: TaskType) -> bool:
        """Check whether a task runs fully offline without cloud API overhead."""
        profile = self.get_profile(task)
        return profile.provider in {"local_rule", "ollama"}

    def summary(self) -> Dict[str, Dict[str, Any]]:
        """Return human-readable routing mapping."""
        return {
            task.value: profile.to_dict()
            for task, profile in self._routing.items()
        }


# Global singleton router instance
_default_router: Optional[ModelRouter] = None


def get_model_router() -> ModelRouter:
    """Retrieve or initialize global ModelRouter singleton."""
    global _default_router
    if _default_router is None:
        _default_router = ModelRouter()
    return _default_router

