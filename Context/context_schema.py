"""Data schemas for the Context reasoning and decision layer."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Literal, Optional


class ScreenState(str, Enum):
    """Categorized situational states recognized by the Context engine."""
    CHROME_PROFILE_PICKER = "chrome_profile_picker"
    CHROME_OCCUPIED_TAB = "chrome_occupied_tab"
    CHROME_NEW_TAB = "chrome_new_tab"
    INSTAGRAM_LOGIN_FORM = "instagram_login_form"
    INSTAGRAM_AUTOFILL_AVAILABLE = "instagram_autofill_available"
    INSTAGRAM_LOGGED_IN = "instagram_logged_in"
    DIALOG_POPUP = "dialog_popup"
    GENERIC_PAGE = "generic_page"
    UNKNOWN = "unknown"


@dataclass
class ActionRecommendation:
    """Action proposed by the Context layer based on situational analysis."""
    action_type: Literal["click_element", "hotkey", "type_text", "wait", "none"]
    target_id: Optional[int] = None
    hotkey: Optional[List[str]] = None
    text: Optional[str] = None
    explanation: str = ""
    params: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action_type": self.action_type,
            "target_id": self.target_id,
            "hotkey": self.hotkey,
            "text": self.text,
            "explanation": self.explanation,
            "params": self.params,
        }


@dataclass
class ContextReport:
    """Analysis result returned by the Context layer.
    
    Contains explicit situational awareness ('situation'), user-facing rationale ('utterance'),
    and the structured next action ('recommendation').
    """
    state: ScreenState
    situation: str
    utterance: str
    recommendation: ActionRecommendation
    confidence: float = 1.0
    active_window: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "state": self.state.value if isinstance(self.state, ScreenState) else str(self.state),
            "situation": self.situation,
            "utterance": self.utterance,
            "recommendation": self.recommendation.to_dict(),
            "confidence": round(float(self.confidence), 3),
            "active_window": self.active_window,
            "metadata": self.metadata,
        }
