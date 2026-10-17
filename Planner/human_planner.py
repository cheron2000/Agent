"""Human-like task planner that translates user goals into sequential step-by-step instructions.

Models how a human performs desktop tasks:
1. Search and launch application from Start / taskbar.
2. Wait for application window to open and focus.
3. Observe screen to assess context (e.g. Profile picker, active tab state).
4. Locate search bar / address bar and click or hotkey into it.
5. Type URL / query with natural human typing velocity using Hands.
6. Submit and verify visual post-conditions with Eyes.
"""

import logging
import re
import time
from typing import Any, Callable, Dict, List, Optional

from .schema import Plan, PlanStep, StepActionType, StepStatus

logger = logging.getLogger("planner.human_planner")


class HumanLikePlanner:
    """Generates and executes human-like step-by-step task plans for desktop operations."""

    def __init__(self, controller: Optional[Any] = None):
        self.controller = controller

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
        )

        # -------------------------------------------------------------
        # STEP 4: Wait for application window to appear and focus it
        # -------------------------------------------------------------
        plan.add_step(
            intent=f"Wait and bring {window_title} to foreground focus",
            action_type=StepActionType.FOCUS_WINDOW,
            parameters={"window_title": window_title, "timeout": 5.0},
            expected_outcome=f"{window_title} window in foreground",
            utterance=f"Waiting for {window_title} to appear and bringing it into focus.",
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
            )

            # -------------------------------------------------------------
            # STEP 9: Verify page load post-condition
            # -------------------------------------------------------------
            expected_keywords = []
            if "hackthebox" in target_dest or "hack the box" in clean_goal:
                expected_keywords = ["hack the box", "hackthebox", "cybersecurity", "htb"]
            elif "youtube" in target_dest or "youtube" in clean_goal:
                expected_keywords = ["youtube", "search"]
            else:
                domain_part = re.sub(r'https?://(www\.)?', '', target_dest).split('/')[0].split('.')[0]
                expected_keywords = [domain_part]

            plan.add_step(
                intent="Verify page loaded successfully by observing screen and window title",
                action_type=StepActionType.VERIFY,
                parameters={"expected": expected_keywords, "timeout_s": 8.0},
                expected_outcome=f"Page loaded containing {expected_keywords}",
                utterance=f"Verifying the page finished loading by checking visible text and title.",
            )

        return plan

    def execute_step(self, step: PlanStep, controller: Optional[Any] = None) -> bool:
        """Execute a single atomic plan step and compute its burst time."""
        c = controller or self._get_controller()
        step.status = StepStatus.RUNNING
        t0 = time.perf_counter()

        try:
            act = step.action_type
            params = step.parameters

            if act == StepActionType.HOTKEY:
                keys = params.get("keys", [])
                c.hotkey(*keys)
                time.sleep(0.3)

            elif act == StepActionType.PRESS_KEY:
                key = params.get("key", "enter")
                c.press_key(key)
                time.sleep(0.2)

            elif act == StepActionType.TYPE_TEXT:
                text = params.get("text", "")
                profile = params.get("profile", "natural")
                c.type_text(text, profile=profile)

            elif act == StepActionType.CLICK_ELEMENT:
                el_id = params.get("element_id")
                c.click_element(el_id)

            elif act == StepActionType.CLICK_COORDS:
                x = params.get("x")
                y = params.get("y")
                c.click(x=x, y=y)

            elif act == StepActionType.MOVE_MOUSE:
                x = params.get("x")
                y = params.get("y")
                c.move(x=x, y=y)

            elif act == StepActionType.FOCUS_WINDOW:
                title = params.get("window_title", "")
                timeout = params.get("timeout", 5.0)
                deadline = time.time() + timeout
                focused = False
                while time.time() < deadline:
                    if c.focus(title):
                        focused = True
                        break
                    time.sleep(0.5)
                if not focused:
                    logger.warning("Could not focus window %s within timeout", title)

            elif act == StepActionType.WAIT:
                seconds = params.get("seconds", 1.0)
                time.sleep(seconds)

            elif act == StepActionType.OBSERVE:
                obs = c.observe(annotate=True, mode=params.get("mode", "balanced"))
                if obs and obs.get("annotated_image_path"):
                    step.evidence = obs.get("annotated_image_path")
                # Situational context check
                if hasattr(c, "analyze_context") and c.context:
                    report = c.analyze_context(observation=obs, goal=params.get("goal"))
                    # If occupied tab or profile picker detected, adapt
                    if report.state.value == "chrome_occupied_tab":
                        logger.info("Tab occupied, opening fresh tab via Ctrl+T")
                        c.hotkey("ctrl", "t")
                        time.sleep(0.4)
                    elif report.state.value == "chrome_profile_picker":
                        if report.recommendation.target_id:
                            c.click_element(report.recommendation.target_id)
                        else:
                            c.press_key("enter")
                        time.sleep(1.0)

            elif act == StepActionType.VERIFY:
                expected = params.get("expected", [])
                timeout_s = params.get("timeout_s", 6.0)
                deadline = time.time() + timeout_s
                verified = False

                while time.time() < deadline:
                    active = c.windows().get("active_window", "")
                    if any(kw.lower() in active.lower() for kw in expected):
                        verified = True
                        break
                    # OCR check
                    obs = c.observe(annotate=True, mode="balanced")
                    if obs.get("annotated_image_path"):
                        step.evidence = obs.get("annotated_image_path")
                    text_match = any(
                        any(kw.lower() in (el.get("name") or "").lower() for kw in expected)
                        for el in obs.get("elements", [])
                    )
                    if text_match:
                        verified = True
                        break
                    time.sleep(1.5)

                if not verified:
                    logger.warning("Verification criteria %s not fully matched", expected)

            step.burst_time_ms = round((time.perf_counter() - t0) * 1000.0, 2)
            step.status = StepStatus.COMPLETED
            return True

        except Exception as ex:
            step.burst_time_ms = round((time.perf_counter() - t0) * 1000.0, 2)
            step.status = StepStatus.FAILED
            step.error = str(ex)
            logger.exception("Step %d execution failed: %s", step.step_number, ex)
            return False

    def execute_plan(
        self,
        plan: Plan,
        controller: Optional[Any] = None,
        on_step: Optional[Callable[[PlanStep, str], None]] = None,
    ) -> Plan:
        """Execute all steps in the plan sequentially like a human, computing burst times."""
        c = controller or self._get_controller()
        t_start_plan = time.perf_counter()

        with c.task(f"plan_{int(time.time())}"):
            for idx, step in enumerate(plan.steps):
                plan.current_step = step.step_number

                # Pre-step callback (announce human instruction)
                if on_step:
                    on_step(step, "before")

                success = self.execute_step(step, controller=c)

                # Post-step callback (announce completion & burst time)
                if on_step:
                    on_step(step, "after")

                if not success:
                    logger.warning("Plan halted at step %d: %s", step.step_number, step.error)
                    break

            plan.completed = all(s.status == StepStatus.COMPLETED for s in plan.steps)
            plan.total_burst_time_ms = round((time.perf_counter() - t_start_plan) * 1000.0, 2)

        return plan
