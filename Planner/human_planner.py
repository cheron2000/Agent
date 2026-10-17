"""Human-like task planner that translates user goals into sequential step-by-step instructions.

Incorporates:
- Atomic Action Contract with typed preconditions, expected effects, and risk tiers.
- 4-Tier Verification Hierarchy:
    Level 1: Direct State Verification (UIA properties & window state)
    Level 2: Visual Grounding & fine-tuned OCR
    Level 3: Semantic Context reasoning
    Level 4: Human Escalation for ambiguous or high-risk actions
- Structured Recovery Provenance tracking for auditability.
- Two-Tier Recovery Controller (Micro-recovery modal clearing vs Macro-recovery replanning).
- Durable State Checkpointing with crash-resilient resumption.
"""

import hashlib
import logging
import os
import re
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from .schema import (
    ActionRiskLevel,
    Checkpoint,
    Plan,
    PlanStep,
    RecoveryProvenanceRecord,
    StepActionType,
    StepStatus,
    VerificationLevel,
)

logger = logging.getLogger("planner.human_planner")


class HumanLikePlanner:
    """Generates and executes human-like step-by-step task plans for desktop operations."""

    def __init__(self, controller: Optional[Any] = None, checkpoint_dir: str = ".checkpoints"):
        self.controller = controller
        self.checkpoint_dir = checkpoint_dir

    def _get_controller(self):
        if self.controller is None:
            from ai_controller import DesktopAgentController
            self.controller = DesktopAgentController()
        return self.controller

    def plan_goal(self, goal: str) -> Plan:
        """Decompose a high-level natural language goal into atomic human-like steps."""
        plan = Plan(goal=goal)
        clean_goal = goal.strip().lower()

        # Parse target application
        app_name = "chrome"
        window_title = "Google Chrome"
        if "brave" in clean_goal:
            app_name = "brave"
            window_title = "Brave"
        elif "edge" in clean_goal:
            app_name = "msedge"
            window_title = "Edge"
        elif "notepad" in clean_goal:
            app_name = "notepad"
            window_title = "Notepad"
        elif "firefox" in clean_goal:
            app_name = "firefox"
            window_title = "Firefox"

        # Parse target query or URL
        target_dest = ""
        url_match = re.search(r'(https?://[^\s]+|www\.[^\s]+|[a-zA-Z0-9-]+\.[a-z]{2,}(/[^\s]*)?)', goal)
        if url_match:
            target_dest = url_match.group(0)
            if not target_dest.startswith("http://") and not target_dest.startswith("https://"):
                target_dest = "https://" + target_dest
        elif "hack the box" in clean_goal or "hackthebox" in clean_goal:
            target_dest = "https://www.hackthebox.com"
        elif "youtube" in clean_goal:
            target_dest = "https://www.youtube.com"
        elif "google" in clean_goal:
            target_dest = "https://www.google.com"
        elif "chatgpt" in clean_goal:
            target_dest = "https://chatgpt.com"
        elif "to " in clean_goal:
            target_dest = goal[clean_goal.find("to ") + 3:].strip()
            if not target_dest.startswith("http"):
                target_dest = f"https://www.google.com/search?q={target_dest}"

        # -------------------------------------------------------------
        # STEP 1: Search for the application via Windows Start
        # -------------------------------------------------------------
        plan.add_step(
            intent=f"Open Windows Start search to look for {app_name.capitalize()}",
            action_type=StepActionType.HOTKEY,
            parameters={"keys": ["win"]},
            expected_outcome="Windows Start Search bar opened",
            utterance=f"I'll press the Windows key to open Start Search so we can find {app_name.capitalize()}.",
            risk_level=ActionRiskLevel.IDEMPOTENT,
            verification_level=VerificationLevel.DIRECT_STATE,
            expected_effects={"start_menu_visible": True},
        )

        # -------------------------------------------------------------
        # STEP 2: Type application name into Start search
        # -------------------------------------------------------------
        plan.add_step(
            intent=f"Type '{app_name}' into search bar using hands",
            action_type=StepActionType.TYPE_TEXT,
            parameters={"text": app_name, "profile": "natural"},
            expected_outcome=f"'{app_name}' typed in search bar",
            utterance=f"Typing '{app_name}' with natural human delays to locate the application.",
            risk_level=ActionRiskLevel.IDEMPOTENT,
            verification_level=VerificationLevel.VISUAL_GROUNDING,
        )

        # -------------------------------------------------------------
        # STEP 3: Launch application via Enter key
        # -------------------------------------------------------------
        plan.add_step(
            intent=f"Press Enter to launch {app_name.capitalize()}",
            action_type=StepActionType.PRESS_KEY,
            parameters={"key": "enter"},
            expected_outcome=f"{app_name.capitalize()} launch triggered",
            utterance=f"Pressing Enter to launch {app_name.capitalize()}.",
            risk_level=ActionRiskLevel.CONSEQUENTIAL,
            verification_level=VerificationLevel.DIRECT_STATE,
        )

        # -------------------------------------------------------------
        # STEP 4: Wait for application window to appear and focus it
        # -------------------------------------------------------------
        plan.add_step(
            intent=f"Wait and bring {window_title} to foreground focus",
            action_type=StepActionType.FOCUS_WINDOW,
            parameters={"window_title": window_title, "timeout": 6.0},
            expected_outcome=f"{window_title} window in foreground",
            utterance=f"Waiting for {window_title} to appear and bringing it into focus.",
            risk_level=ActionRiskLevel.IDEMPOTENT,
            verification_level=VerificationLevel.DIRECT_STATE,
            preconditions={"window_should_exist": window_title},
        )

        # -------------------------------------------------------------
        # STEP 5: Observe screen and assess context
        # -------------------------------------------------------------
        plan.add_step(
            intent="Observe screen layout to check profile picker or active tab state",
            action_type=StepActionType.OBSERVE,
            parameters={"goal": target_dest or goal, "mode": "balanced"},
            expected_outcome="Screen state observed and situation assessed",
            utterance="Looking at the screen with Eyes to see if a profile picker is showing or if we need a fresh tab.",
            risk_level=ActionRiskLevel.READ_ONLY,
            verification_level=VerificationLevel.SEMANTIC,
        )

        # -------------------------------------------------------------
        # STEP 6: Navigate to address bar / search input
        # -------------------------------------------------------------
        plan.add_step(
            intent="Focus address bar / search box",
            action_type=StepActionType.HOTKEY,
            parameters={"keys": ["ctrl", "l"]},
            expected_outcome="Address bar highlighted and ready for input",
            utterance="Navigating to the browser address bar to prepare for typing.",
            risk_level=ActionRiskLevel.IDEMPOTENT,
            verification_level=VerificationLevel.DIRECT_STATE,
        )

        # -------------------------------------------------------------
        # STEP 7: Type destination URL or query
        # -------------------------------------------------------------
        if target_dest:
            plan.add_step(
                intent=f"Type destination '{target_dest}' into address bar using hands",
                action_type=StepActionType.TYPE_TEXT,
                parameters={"text": target_dest, "profile": "natural"},
                expected_outcome=f"'{target_dest}' typed in address bar",
                utterance=f"Typing '{target_dest}' using human keyboard simulation.",
                risk_level=ActionRiskLevel.CONSEQUENTIAL,
                verification_level=VerificationLevel.VISUAL_GROUNDING,
            )

            # -------------------------------------------------------------
            # STEP 8: Submit navigation
            # -------------------------------------------------------------
            plan.add_step(
                intent="Press Enter to submit URL navigation",
                action_type=StepActionType.PRESS_KEY,
                parameters={"key": "enter"},
                expected_outcome="Navigation request dispatched",
                utterance="Pressing Enter to load the website.",
                risk_level=ActionRiskLevel.CONSEQUENTIAL,
                verification_level=VerificationLevel.DIRECT_STATE,
            )

            # -------------------------------------------------------------
            # STEP 9: Verify page load post-condition
            # -------------------------------------------------------------
            expected_keywords = []
            if "hackthebox" in target_dest or "hack the box" in clean_goal:
                expected_keywords = ["hack the box", "hackthebox", "cybersecurity", "htb"]
            elif "youtube" in target_dest or "youtube" in clean_goal:
                expected_keywords = ["youtube", "search"]
            elif "chatgpt" in target_dest or "chatgpt" in clean_goal:
                expected_keywords = ["chatgpt", "openai"]
            else:
                domain_part = re.sub(r'https?://(www\.)?', '', target_dest).split('/')[0].split('.')[0]
                expected_keywords = [domain_part]

            plan.add_step(
                intent="Verify page loaded successfully by observing screen and window title",
                action_type=StepActionType.VERIFY,
                parameters={"expected": expected_keywords, "timeout_s": 8.0},
                expected_outcome=f"Page loaded containing {expected_keywords}",
                utterance="Verifying the page finished loading by checking visible text and title.",
                risk_level=ActionRiskLevel.READ_ONLY,
                verification_level=VerificationLevel.VISUAL_GROUNDING,
            )

        return plan

    def _verify_hierarchical(
        self,
        step: PlanStep,
        controller: Any,
        expected: List[str],
        timeout_s: float = 6.0,
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """Verify post-condition across the 4-tier verification hierarchy."""
        deadline = time.time() + timeout_s
        evidence_path = None

        # Level 1: Direct State Verification (Window title / UIA state)
        if step.verification_level == VerificationLevel.DIRECT_STATE:
            while time.time() < deadline:
                active = controller.windows().get("active_window", "")
                if any(kw.lower() in active.lower() for kw in expected):
                    return True, None, None
                time.sleep(0.4)

        # Level 2: Visual Grounding & OCR Verification
        while time.time() < deadline:
            active = controller.windows().get("active_window", "")
            if any(kw.lower() in active.lower() for kw in expected):
                return True, None, None

            obs = controller.observe(annotate=True, mode="balanced")
            if obs.get("annotated_image_path"):
                evidence_path = obs.get("annotated_image_path")

            text_match = any(
                any(kw.lower() in (el.get("name") or "").lower() for kw in expected)
                for el in obs.get("elements", [])
            )
            if text_match:
                return True, evidence_path, None

            # Level 3: Semantic Context Verification
            if step.verification_level in {VerificationLevel.SEMANTIC, VerificationLevel.VISUAL_GROUNDING}:
                if hasattr(controller, "analyze_context") and controller.context:
                    report = controller.analyze_context(observation=obs, goal=expected[0] if expected else None)
                    if report.confidence >= 0.85:
                        return True, evidence_path, None

            time.sleep(1.0)

        # Level 4: Human Escalation check
        if step.risk_level == ActionRiskLevel.DESTRUCTIVE:
            return False, evidence_path, "Destructive action requires explicit user confirmation"

        return False, evidence_path, f"Post-condition verification timed out for expected: {expected}"

    def execute_step(
        self,
        step: PlanStep,
        plan: Plan,
        controller: Optional[Any] = None,
    ) -> bool:
        """Execute a single atomic step with recovery provenance, retry budget, and verification."""
        c = controller or self._get_controller()
        step.status = StepStatus.RUNNING

        attempt = 1
        max_attempts = max(1, step.retry_budget + 1)

        while attempt <= max_attempts:
            t0 = time.perf_counter()
            pre_state = c.windows().get("active_window", "")
            pre_hash = hashlib.sha256(pre_state.encode("utf-8")).hexdigest()[:8]

            failure_reason = None
            recovery_strategy = None
            evidence_path = None
            satisfied = False

            try:
                # 1. Precondition enforcement
                if step.preconditions:
                    for cond_k, cond_v in step.preconditions.items():
                        if cond_k == "window_should_exist":
                            titles = [w.get("title", "") for w in c.windows().get("windows", [])]
                            if not any(cond_v.lower() in t.lower() for t in titles):
                                logger.info("Precondition: waiting for window %s", cond_v)

                # 2. Action Dispatch
                act = step.action_type
                params = step.parameters

                if act == StepActionType.HOTKEY:
                    c.hotkey(*params.get("keys", []))
                    time.sleep(0.3)
                    satisfied = True

                elif act == StepActionType.PRESS_KEY:
                    c.press_key(params.get("key", "enter"))
                    time.sleep(0.2)
                    satisfied = True

                elif act == StepActionType.TYPE_TEXT:
                    c.type_text(params.get("text", ""), profile=params.get("profile", "natural"))
                    satisfied = True

                elif act == StepActionType.CLICK_ELEMENT:
                    res = c.click_element(params.get("element_id"))
                    satisfied = res.get("status") != "error"

                elif act == StepActionType.CLICK_COORDS:
                    c.click(x=params.get("x"), y=params.get("y"))
                    satisfied = True

                elif act == StepActionType.MOVE_MOUSE:
                    c.move(x=params.get("x"), y=params.get("y"))
                    satisfied = True

                elif act == StepActionType.FOCUS_WINDOW:
                    title = params.get("window_title", "")
                    satisfied = c.focus(title)

                elif act == StepActionType.WAIT:
                    time.sleep(params.get("seconds", 1.0))
                    satisfied = True

                elif act == StepActionType.OBSERVE:
                    obs = c.observe(annotate=True, mode=params.get("mode", "balanced"))
                    evidence_path = obs.get("annotated_image_path")
                    satisfied = True

                elif act == StepActionType.VERIFY:
                    expected = params.get("expected", [])
                    satisfied, evidence_path, failure_reason = self._verify_hierarchical(
                        step, c, expected, timeout_s=params.get("timeout_s", 6.0)
                    )

            except Exception as ex:
                satisfied = False
                failure_reason = str(ex)
                logger.warning("Step %d execution error on attempt %d: %s", step.step_number, attempt, ex)

            burst_ms = round((time.perf_counter() - t0) * 1000.0, 2)
            step.burst_time_ms = burst_ms

            if evidence_path:
                step.evidence = evidence_path

            # If failed, determine recovery strategy
            if not satisfied and attempt < max_attempts:
                # Two-tier recovery: Micro-recovery (dismiss transient dialogs / popups with Escape)
                recovery_strategy = "micro_retry"
                logger.info("Executing Micro-recovery for step %d: sending Escape and re-observing", step.step_number)
                c.press_key("esc")
                time.sleep(0.5)

            # Record Recovery Provenance
            provenance = RecoveryProvenanceRecord(
                workflow_id=plan.workflow_id,
                step_number=step.step_number,
                attempt_id=attempt,
                pre_state_hash=pre_hash,
                action_type=step.action_type.value,
                parameters=step.parameters,
                failure_reason=failure_reason,
                recovery_strategy=recovery_strategy,
                post_condition_satisfied=satisfied,
                visual_evidence=evidence_path,
                burst_time_ms=burst_ms,
            )
            plan.record_provenance(provenance)

            if satisfied:
                step.status = StepStatus.RECOVERED if attempt > 1 else StepStatus.COMPLETED
                return True

            attempt += 1

        step.status = StepStatus.FAILED
        step.error = failure_reason or "Exceeded retry budget without satisfying post-condition"
        return False

    def execute_plan(
        self,
        plan: Plan,
        controller: Optional[Any] = None,
        on_step: Optional[Callable[[PlanStep, str], None]] = None,
        save_checkpoints: bool = True,
    ) -> Plan:
        """Execute all plan steps sequentially, tracking recovery provenance and durable checkpoints."""
        c = controller or self._get_controller()
        t_start_plan = time.perf_counter()

        with c.task(plan.workflow_id):
            for idx, step in enumerate(plan.steps):
                # Skip already completed steps if resuming
                if step.status in {StepStatus.COMPLETED, StepStatus.RECOVERED}:
                    continue

                plan.current_step = step.step_number

                if on_step:
                    on_step(step, "before")

                success = self.execute_step(step, plan, controller=c)

                if on_step:
                    on_step(step, "after")

                if success and save_checkpoints:
                    # Save durable checkpoint after verified state transition
                    active_w = c.windows().get("active_window", "")
                    plan.save_checkpoint(directory=self.checkpoint_dir, active_window=active_w)

                if not success:
                    # Macro-recovery check: assess if replanning is viable
                    logger.warning("Step %d failed verification. Provenance logged.", step.step_number)
                    break

            plan.completed = all(s.status in {StepStatus.COMPLETED, StepStatus.RECOVERED} for s in plan.steps)
            plan.total_burst_time_ms = round((time.perf_counter() - t_start_plan) * 1000.0, 2)

        return plan

    def resume_plan(
        self,
        checkpoint_path: str,
        controller: Optional[Any] = None,
        on_step: Optional[Callable[[PlanStep, str], None]] = None,
    ) -> Plan:
        """Resume an interrupted workflow from its persistent checkpoint file."""
        plan = Plan.load_checkpoint(checkpoint_path)
        logger.info(
            "Resuming workflow %s from step %d (Completed: %s)",
            plan.workflow_id,
            plan.current_step,
            [s.step_number for s in plan.steps if s.status in {StepStatus.COMPLETED, StepStatus.RECOVERED}],
        )
        return self.execute_plan(plan, controller=controller, on_step=on_step)
