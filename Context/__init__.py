"""Context Layer for Desktop Agent.

Sits between Eyes (Perception) and Hands (Action) to analyze screen situation,
formulate human-understandable reasoning ("utterances"), and determine the next adaptive action.
"""

try:
    from .context_schema import ScreenState, ActionRecommendation, ContextReport
    from .analyzer import ContextAnalyzer
except ImportError:
    from Context.context_schema import ScreenState, ActionRecommendation, ContextReport
    from Context.analyzer import ContextAnalyzer

__all__ = [
    "ScreenState",
    "ActionRecommendation",
    "ContextReport",
    "ContextAnalyzer",
]
