"""Reliable step-driven desktop workflow execution.

The runner is intentionally decoupled from the Windows implementation. It accepts
any controller exposing the DesktopAgentController-style methods and enforces the
project's Observe -> Act -> Verify loop for each step.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Optional, Protocol


class Controller(Protocol):
    def observe(self, **kwargs: Any) -> Dict[str, Any]: ...
    def transcribe(self, detailed: bool = False) -> Dict[str, Any]: ...
    def windows(self) -> Dict[str, Any]: ...
    def click_element(self, element_id: int, **kwargs: Any) -> Dict[str, Any]: ...
    def type_text(self, text: str, **kwargs: Any) -> Dict[str, Any]: ...
    def paste_text(self, text: str, **kwargs: Any) -> Any: ...
    def press_key(self, key: str) -> Any: ...
    def hotkey(self, *keys: str) -> Any: ...
    def scroll(self, clicks: int, **kwargs: Any) -> Dict[str, Any]: ...
    def focus(self, window_title: str) -> bool: ...
    def wait_for_text(self, target: str, timeout_s: float = 5.0) -> Dict[str, Any]: ...


class WorkflowError(RuntimeError):
    """Raised when a workflow step cannot be verified after its retries."""


@dataclass(frozen=True)
class Verification:
    """A post-condition checked after an action."""

    type: str
    expected: Any
    timeout_s: float = 5.0

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "Verification":
        kind = value.get("type")
        if not kind:
            raise ValueError("verification.type is required")
        if "expected" not in value:
            raise ValueError("verification.expected is required")
        return cls(type=str(kind), expected=value["expected"], timeout_s=float(value.get("timeout_s", 5.0)))


@dataclass(frozen=True)
class WorkflowStep:
    """One atomic action and its required post-condition."""

    intent: str
    action: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    verification: Optional[Verification] = None
    recovery: Optional[Dict[str, Any]] = None
    retries: int = 2
    wait_seconds: float = 0.0

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "WorkflowStep":
        if not value.get("intent"):
            raise ValueError("step.intent is required")
        if not value.get("action"):
            raise ValueError("step.action is required")
        raw_verification = value.get("verification")
        return cls(
            intent=str(value["intent"]),
            action=str(value["action"]),
            parameters=dict(value.get("parameters", {})),
            verification=Verification.from_dict(raw_verification) if raw_verification else None,
            recovery=dict(value["recovery"]) if value.get("recovery") else None,
            retries=max(0, int(value.get("retries", 2))),
            wait_seconds=max(0.0, float(value.get("wait_seconds", 0.0))),
        )


@dataclass
class StepResult:
    step_number: int
    intent: str
    success: bool
    attempts: int
    evidence: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_number": self.step_number,
            "intent": self.intent,
            "success": self.success,
            "attempts": self.attempts,
            "evidence": self.evidence,
            "error": self.error,
        }


class WorkflowRunner:
    """Execute atomic desktop actions with bounded retries and verification."""

    def __init__(self, controller: Controller, *, sleep=time.sleep):
        self.controller = controller
        self._sleep = sleep

    def run(self, steps: Iterable[WorkflowStep | Mapping[str, Any]], *, stop_on_error: bool = True) -> Dict[str, Any]:
        normalized = [step if isinstance(step, WorkflowStep) else WorkflowStep.from_dict(step) for step in steps]
        results: List[StepResult] = []
        for number, step in enumerate(normalized, start=1):
            result = self.run_step(number, step)
            results.append(result)
            if not result.success and stop_on_error:
                break
        return {
            "success": bool(results) and all(item.success for item in results),
            "completed_steps": sum(item.success for item in results),
            "total_steps": len(normalized),
            "results": [item.to_dict() for item in results],
        }

    def run_step(self, step_number: int, step: WorkflowStep) -> StepResult:
        last_error: Optional[str] = None
        attempts = step.retries + 1
        for attempt in range(1, attempts + 1):
            try:
                action_result = self._execute(step.action, step.parameters)
                if step.wait_seconds:
                    self._sleep(step.wait_seconds)
                evidence = self._verify(step.verification)
                return StepResult(step_number, step.intent, True, attempt, {"action": action_result, **evidence})
            except Exception as exc:  # noqa: BLE001 - convert failures into structured step results
                last_error = str(exc)
                if attempt < attempts and step.recovery:
                    self._execute(step.recovery["action"], dict(step.recovery.get("parameters", {})))
        return StepResult(step_number, step.intent, False, attempts, error=last_error)

    def _execute(self, action: str, parameters: Mapping[str, Any]) -> Any:
        if action == "focus":
            return {"success": bool(self.controller.focus(str(parameters["window_title"]))) }
        if action == "click_element":
            return self.controller.click_element(int(parameters["element_id"]))
        if action == "type_text":
            return self.controller.type_text(str(parameters["text"]), profile=str(parameters.get("profile", "natural")))
        if action == "paste_text":
            return self.controller.paste_text(str(parameters["text"]), restore_clipboard=bool(parameters.get("restore_clipboard", True)))
        if action == "press_key":
            return self.controller.press_key(str(parameters["key"]))
        if action == "hotkey":
            keys = parameters.get("keys")
            if not isinstance(keys, list) or not keys:
                raise ValueError("hotkey requires a non-empty parameters.keys list")
            return self.controller.hotkey(*(str(key) for key in keys))
        if action == "scroll":
            return self.controller.scroll(int(parameters["clicks"]))
        if action == "wait":
            self._sleep(max(0.0, float(parameters.get("seconds", 1.0))))
            return {"success": True, "action": "wait"}
        raise ValueError(f"Unsupported workflow action: {action}")

    def _verify(self, verification: Optional[Verification]) -> Dict[str, Any]:
        if verification is None:
            raise ValueError("Every step must define a verification post-condition")
        expected = verification.expected
        if verification.type == "text_contains":
            values = [expected] if isinstance(expected, str) else list(expected)
            result = self.controller.wait_for_text(str(values[0]), timeout_s=verification.timeout_s)
            text = result.get("text", "") if isinstance(result, dict) else ""
            matched = bool(result.get("success")) if isinstance(result, dict) else False
            if not matched:
                matched = any(str(value).casefold() in str(text).casefold() for value in values)
            if not matched:
                raise WorkflowError(f"Expected text not found: {values}")
            return {"verification": {"type": verification.type, "matched": values}}
        if verification.type == "text_not_contains":
            text = self.controller.transcribe().get("text", "")
            values = [expected] if isinstance(expected, str) else list(expected)
            found = [value for value in values if str(value).casefold() in str(text).casefold()]
            if found:
                raise WorkflowError(f"Unexpected text found: {found}")
            return {"verification": {"type": verification.type, "matched": True}}
        if verification.type == "active_window_contains":
            active = self.controller.windows().get("active_window", "")
            if str(expected).casefold() not in str(active).casefold():
                raise WorkflowError(f"Active window does not contain {expected!r}: {active!r}")
            return {"verification": {"type": verification.type, "active_window": active}}
        if verification.type == "element_name_contains":
            observation = self.controller.observe(annotate=False)
            elements = observation.get("elements", [])
            values = [expected] if isinstance(expected, str) else list(expected)
            names = [str(element.get("name", "")) for element in elements]
            if not any(str(value).casefold() in name.casefold() for value in values for name in names):
                raise WorkflowError(f"No element matched {values}")
            return {"verification": {"type": verification.type, "elements": names}}
        raise ValueError(f"Unsupported verification type: {verification.type}")
