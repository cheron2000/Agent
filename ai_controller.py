"""Direct controller for an agent operating the real Windows desktop.

This module deliberately has no virtual canvas or browser sandbox.  It uses
Eyes for desktop perception and AgentHands for mouse/keyboard actions on the
currently visible Windows desktop.
"""

import logging
import os
import sys
from contextlib import contextmanager
import time
from typing import Any, Dict, List, Optional, Tuple

ROOT = os.path.dirname(__file__)
sys.path.extend([os.path.join(ROOT, "Eyes"), os.path.join(ROOT, "Hands")])

# ---------------------------------------------------------------------------
# Module-level logger
# ---------------------------------------------------------------------------

_log_formatter = logging.Formatter("%(asctime)s %(levelname)s [ai_controller] %(message)s")

_file_handler = logging.FileHandler(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "err.log"),
    encoding="utf-8",
)
_file_handler.setFormatter(_log_formatter)

_console_handler = logging.StreamHandler()
_console_handler.setFormatter(_log_formatter)

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
logger.addHandler(_file_handler)
logger.addHandler(_console_handler)

import eyes
from agent_hands.engine import TypingEngine
from agent_hands.keyboard import fast_paste, press_single_key, execute_hotkey
from agent_hands.mouse import click, move_to, scroll
from agent_hands.windows import focus_window, get_active_window_title, list_windows

try:
    from Context import ContextAnalyzer, ContextReport
except ImportError:
    try:
        from .Context import ContextAnalyzer, ContextReport
    except ImportError:
        ContextAnalyzer = None
        ContextReport = None

try:
    from action_expectations import ActionExpectation, ActionIntent, ActionRiskLevel, ActionState
    from action_verifier import ActionVerifier, VerificationEvidence, VerificationStatus
    from action_recovery import ActionRecoveryDecider, RecoveryDecision, RecoveryStrategy
    from action_orchestrator import ActionOrchestrator
except ImportError:
    try:
        from .action_expectations import ActionExpectation, ActionIntent, ActionRiskLevel, ActionState
        from .action_verifier import ActionVerifier, VerificationEvidence, VerificationStatus
        from .action_recovery import ActionRecoveryDecider, RecoveryDecision, RecoveryStrategy
        from .action_orchestrator import ActionOrchestrator
    except ImportError:
        ActionExpectation = None
        ActionIntent = None
        ActionRiskLevel = None
        ActionState = None
        ActionVerifier = None
        VerificationEvidence = None
        VerificationStatus = None
        ActionRecoveryDecider = None
        RecoveryDecision = None
try:
    from Planner.goal_schema import ExecutionPlan, PlanStep
    from Planner.goal_executor import AutonomousGoalExecutor
except (ImportError, ValueError):
    ExecutionPlan = None
    PlanStep = None
    AutonomousGoalExecutor = None


class DesktopAgentController:
    """Perceive and operate the user's actual desktop through Eyes, Context, and AgentHands."""

    def __init__(self):
        self.context = ContextAnalyzer() if ContextAnalyzer else None
        self.verifier = ActionVerifier() if ActionVerifier else None
        self.recovery_decider = ActionRecoveryDecider() if ActionRecoveryDecider else None
        self.orchestrator = ActionOrchestrator(
            controller=self,
            verifier=self.verifier,
            recovery_decider=self.recovery_decider,
        ) if ActionOrchestrator else None
        self.goal_executor = AutonomousGoalExecutor(
            orchestrator=self.orchestrator,
        ) if AutonomousGoalExecutor and self.orchestrator else None

    @contextmanager
    def task(self, task_name: str = "desktop_task"):
        """Track screenshots generated during a task and clean them on exit."""
        session = eyes.start_task(task_name)
        try:
            yield self
        finally:
            eyes.end_task()

    # Perception
    def screen_info(self) -> Dict[str, Any]:
        return eyes.get_screen_info()

    def capture(self, save: bool = True) -> Dict[str, Any]:
        return eyes.capture(save=save)

    def transcribe(self, detailed: bool = False) -> Dict[str, Any]:
        return eyes.read_text(detailed=detailed)

    def find(self, target: str, min_confidence: int = 30) -> Dict[str, Any]:
        return eyes.find_on_screen(target, min_confidence=min_confidence)

    def describe(self, prompt: Optional[str] = None) -> Dict[str, Any]:
        return eyes.describe(prompt=prompt)

    def observe(
        self,
        save_annotated: bool = True,
        max_elements: int = 100,
        annotate: Optional[bool] = None,
        mode: str = "balanced",
        compact: bool = False,
    ) -> Dict[str, Any]:
        """Capture unified observation with numbered UI elements for LLM grounding."""
        if annotate is not None:
            save_annotated = annotate
        return eyes.observe(
            save_annotated=save_annotated,
            max_elements=max_elements,
            mode=mode,
            compact=compact,
        )

    def zoom(
        self,
        region: Optional[List[int]] = None,
        element_id: Optional[int] = None,
        scale: float = 3.0,
    ) -> Dict[str, Any]:
        """Crop and zoom into a bounding box or element ID with high-resolution OCR."""
        return eyes.zoom(region=region, element_id=element_id, scale=scale)

    def wait_for_text(self, target: str, timeout_s: float = 5.0) -> Dict[str, Any]:
        """Wait until target text appears on screen."""
        return eyes.wait_for_text(target=target, timeout_s=timeout_s)

    def ground_target(self, instruction: str, min_confidence: float = 0.4) -> Dict[str, Any]:
        """Locate candidates for a visual or icon-only control matching natural language instruction."""
        return eyes.ground_target(instruction=instruction, min_confidence=min_confidence)


    def click_element(
        self,
        element_id: int,
        button: str = "left",
        clicks: int = 1,
        observation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Click an element by its observation ID without computing pixel coordinates."""
        coords = eyes.resolve_element_center(element_id, observation_id=observation_id)
        if not coords:
            return {"success": False, "error": f"Element ID {element_id} not found in observation"}
        cx, cy = coords
        return click(x=cx, y=cy, button=button, clicks=clicks)

    def resolve_element_center(
        self,
        element_id: int,
        observation_id: Optional[str] = None,
    ) -> Optional[Tuple[int, int]]:
        """Resolve element ID to physical screen center coordinates (cx, cy)."""
        return eyes.resolve_element_center(element_id, observation_id=observation_id)

    def windows(self) -> Dict[str, Any]:
        return {
            "active_window": get_active_window_title(),
            "windows": list_windows(),
        }


    # Real desktop input
    def focus(self, window_title: str) -> bool:
        return focus_window(window_title)

    def move(self, x: int, y: int, duration: float = 0.2) -> Dict[str, Any]:
        return move_to(x=x, y=y, duration=duration)

    def click(
        self,
        x: Optional[int] = None,
        y: Optional[int] = None,
        button: str = "left",
        clicks: int = 1,
    ) -> Dict[str, Any]:
        return click(x=x, y=y, button=button, clicks=clicks)

    def scroll(self, clicks: int, x: Optional[int] = None, y: Optional[int] = None) -> Dict[str, Any]:
        return scroll(clicks=clicks, x=x, y=y, smooth=True)

    def type_text(self, text: str, profile: str = "natural", typos: bool = False) -> Dict[str, Any]:
        """Send simulated keyboard input to the active Windows application."""
        return TypingEngine(profile=profile).type_text(text=text, introduce_typos=typos)
    def paste_text(self, text: str, restore_clipboard: bool = False) -> None:
        """Paste bulk text through the clipboard instead of simulating each key.

        Prefer this for long emails, prompts, and reports. Use type_text() when
        realistic per-key input is specifically needed by the target application.
        """
        fast_paste(text, restore_clipboard=restore_clipboard)

    def press_key(self, key: str) -> None:
        press_single_key(key)

    def hotkey(self, *keys: str) -> None:
        """Execute a key combination with natural human staggering (e.g. 'ctrl', 't')."""
        execute_hotkey(list(keys))

    # â”€â”€ Context Layer Integration â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    def analyze_context(self, observation: Optional[Any] = None, goal: Optional[str] = None) -> Any:
        """Analyze current screen context, formulate situational rationale, and suggest next action."""
        if self.context is None:
            raise RuntimeError("Context engine is not available.")
        obs = observation if observation is not None else self.observe(annotate=True)
        return self.context.analyze(obs, goal=goal)

    def step_with_context(self, goal: Optional[str] = None, execute: bool = True) -> Dict[str, Any]:
        """Perform one autonomous OODA loop step: Observe -> Contextualize -> Act.
        
        Analyzes the current screen, logs the human-readable utterance (reasoning),
        and executes the recommended action if execute=True.
        """
        obs = self.observe(annotate=True)
        report = self.analyze_context(observation=obs, goal=goal)
        logger.info("[Context] %s", report.utterance)

        action_result = None
        if execute and report.recommendation:
            rec = report.recommendation
            act_type = rec.action_type
            if act_type == "click_element" and rec.target_id is not None:
                action_result = self.click_element(rec.target_id)
            elif act_type == "hotkey" and rec.hotkey:
                self.hotkey(*rec.hotkey)
                action_result = {"status": "success", "action": "hotkey", "keys": rec.hotkey}
            elif act_type == "type_text" and rec.text:
                action_result = self.type_text(rec.text)
            elif act_type == "wait":
                time.sleep(rec.params.get("seconds", 2.0))
                action_result = {"status": "success", "action": "wait"}

        return {
            "success": True,
            "report": report.to_dict(),
            "utterance": report.utterance,
            "action_result": action_result,
            "executed": execute,
        }

    # ── Action Verification & Recovery Pipeline ───────────────────────────
    def execute_verified_action(
        self,
        intent: Any,
        pre_observation: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Execute an action and verify its outcome using fresh UI evidence.
        Workflow: PREPARED -> OBSERVE (pre) -> DISPATCH -> OBSERVE (post) -> VERIFY -> RECOVERY.
        """
        if self.verifier is None:
            raise RuntimeError("ActionVerifier is not available.")

        pre_obs = pre_observation if pre_observation is not None else self.observe(annotate=False)
        if hasattr(intent, "state"):
            intent.state = ActionState.DISPATCHED

        dispatch_result: Dict[str, Any] = {"success": False}
        act_type = getattr(intent, "action_type", "")
        params = getattr(intent, "parameters", {}) or {}

        try:
            if act_type == "click_element" and getattr(intent, "target_id", None) is not None:
                dispatch_result = self.click_element(
                    intent.target_id,
                    button=params.get("button", "left"),
                    clicks=params.get("clicks", 1),
                )
            elif act_type == "click_coords":
                dispatch_result = self.click(
                    x=params.get("x"),
                    y=params.get("y"),
                    button=params.get("button", "left"),
                    clicks=params.get("clicks", 1),
                )
            elif act_type == "type_text":
                dispatch_result = self.type_text(
                    text=params.get("text", ""),
                    profile=params.get("profile", "natural"),
                )
            elif act_type == "press_key":
                self.press_key(params.get("key", "enter"))
                dispatch_result = {"success": True, "action": "press_key", "key": params.get("key", "enter")}
            elif act_type == "hotkey":
                keys = params.get("keys", [])
                self.hotkey(*keys)
                dispatch_result = {"success": True, "action": "hotkey", "keys": keys}
            elif act_type == "focus_window":
                win_target = params.get("title") or getattr(intent, "target_query", None)
                ok = self.focus(win_target)
                dispatch_result = {"success": ok, "action": "focus_window", "title": win_target}
            elif act_type == "scroll":
                dispatch_result = self.scroll(
                    clicks=params.get("clicks", -3),
                    x=params.get("x"),
                    y=params.get("y"),
                )
            else:
                dispatch_result = {"success": False, "error": f"Unknown action type: {act_type}"}
        except Exception as ex:
            dispatch_result = {"success": False, "error": str(ex)}

        # Small physical stabilization pause
        time.sleep(0.3)

        # Fresh post-action observation
        post_obs = self.observe(annotate=False)

        # Verify outcome against fresh evidence
        evidence = self.verifier.verify(intent, pre_obs, dispatch_result, post_obs)

        recovery_decision = None
        if evidence.status != VerificationStatus.CONFIRMED and self.recovery_decider:
            recovery_decision = self.recovery_decider.decide(
                intent,
                evidence,
                pre_obs=pre_obs,
                post_obs=post_obs,
            )

        return {
            "success": evidence.status == VerificationStatus.CONFIRMED,
            "intent": intent.to_dict() if hasattr(intent, "to_dict") else str(intent),
            "dispatch_result": dispatch_result,
            "verification": evidence.to_dict(),
            "recovery_decision": recovery_decision.to_dict() if recovery_decision else None,
        }

    def orchestrate_action(
        self,
        intent: Any,
        pre_observation: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Orchestrate an action with closed-loop target resolution, verification, and recovery."""
        if self.orchestrator is None:
            raise RuntimeError("ActionOrchestrator is not available.")
        return self.orchestrator.execute_step(intent, pre_observation=pre_observation)

    def execute_goal(self, plan: Any) -> Dict[str, Any]:
        """Execute a multi-step DAG plan with durable SQLite checkpointing and compensatory recovery."""
        if self.goal_executor is None:
            raise RuntimeError("AutonomousGoalExecutor is not available.")
        res = self.goal_executor.execute_plan(plan)
        return res.to_dict()


if __name__ == "__main__":
    controller = DesktopAgentController()
    logger.info("%s", controller.screen_info())




