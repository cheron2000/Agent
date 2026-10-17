"""Context reasoning and situational decision analyzer."""

from typing import Any, Dict, List, Optional, Tuple

try:
    from .context_schema import ActionRecommendation, ContextReport, ScreenState
except ImportError:
    from Context.context_schema import ActionRecommendation, ContextReport, ScreenState


class ContextAnalyzer:
    """Analyzes desktop observations, formulates situational reasoning, and determines next action."""

    def analyze(
        self,
        observation: Any,
        goal: Optional[str] = None,
    ) -> ContextReport:
        """Analyze an observation (Observation dataclass or dict) and return a ContextReport."""
        obs_dict: Dict[str, Any]
        if hasattr(observation, "to_dict"):
            obs_dict = observation.to_dict()
        elif isinstance(observation, dict):
            obs_dict = observation
        else:
            obs_dict = {}

        active_window = obs_dict.get("active_window", "") or ""
        elements = obs_dict.get("elements", []) or []

        # 1. Popups & Dialogs (must be checked first because dialogs block the screen)
        dialog_report = self._check_dialog_popup(active_window, elements)
        if dialog_report:
            return dialog_report

        # 2. Profile Picker detection (e.g. Chrome "Who's using Chrome?")
        profile_report = self._check_profile_picker(active_window, elements)
        if profile_report:
            return profile_report

        # 3. Specific Application Workflows (e.g. Instagram authentication flow)
        insta_report = self._check_instagram_flow(active_window, elements, goal)
        if insta_report:
            return insta_report

        # 4. Chrome tab occupancy check (occupied vs new tab)
        tab_report = self._check_tab_occupancy(active_window, elements, goal)
        if tab_report:
            return tab_report

        # 5. Default generic observation
        return ContextReport(
            state=ScreenState.GENERIC_PAGE,
            situation=f"Active window is '{active_window}' with {len(elements)} detected UI elements.",
            utterance=f"Window '{active_window}' is active. Ready for next step.",
            recommendation=ActionRecommendation(
                action_type="none",
                explanation="No specific automated action triggered; awaiting instructions.",
            ),
            active_window=active_window,
            confidence=0.8,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Sub-analyzers
    # ─────────────────────────────────────────────────────────────────────────

    def _check_profile_picker(
        self, active_window: str, elements: List[Dict[str, Any]]
    ) -> Optional[ContextReport]:
        """Detect if a browser profile picker is showing."""
        win_lower = active_window.lower()
        is_picker_window = any(
            phrase in win_lower
            for phrase in ["who's using chrome", "choose a profile", "chrome profiles", "profile picker"]
        )

        # Check for profile elements
        profile_candidates = []
        default_candidate = None
        for el in elements:
            name = (el.get("name") or "").strip()
            role = el.get("role", "")
            lower = name.lower()
            if any(term in lower for term in ["who's using chrome", "choose a profile"]):
                is_picker_window = True
            if role in ["Button", "ListItem", "Group"] and any(
                p in lower for p in ["profile", "person ", "guest", "add profile", "user ", "default", "arpita"]
            ):
                profile_candidates.append(el)
                if "default" in lower or not default_candidate:
                    default_candidate = el

        if is_picker_window or len(profile_candidates) >= 2:
            chosen_el = default_candidate or (profile_candidates[0] if profile_candidates else None)
            target_id = chosen_el.get("id") if chosen_el else None
            target_name = chosen_el.get("name") if chosen_el else "default profile"

            return ContextReport(
                state=ScreenState.CHROME_PROFILE_PICKER,
                situation="I see multiple Chrome profiles on screen.",
                utterance=f"I see multiple Chrome profiles. I'll select the default profile ({target_name}) and use it to proceed.",
                recommendation=ActionRecommendation(
                    action_type="click_element" if target_id else "none",
                    target_id=target_id,
                    explanation=f"Clicking profile '{target_name}' to enter Chrome.",
                ),
                active_window=active_window,
                confidence=0.95,
            )

        return None

    def _check_tab_occupancy(
        self, active_window: str, elements: List[Dict[str, Any]], goal: Optional[str]
    ) -> Optional[ContextReport]:
        """Detect whether Chrome is open on an existing/occupied tab or a clean New Tab."""
        win_lower = active_window.lower()
        if "chrome" not in win_lower and "browser" not in win_lower:
            return None

        # Look for the active tab element
        active_tab_title = ""
        new_tab_btn_id = None

        for el in elements:
            role = el.get("role", "")
            name = el.get("name") or ""
            if role == "TabItem" and name:
                # Top tab bar item
                if not active_tab_title:
                    active_tab_title = name
            if role == "Button" and "new tab" in name.lower():
                new_tab_btn_id = el.get("id")

        # Determine tab clean vs occupied
        is_clean_tab = "new tab" in win_lower or "new tab" in active_tab_title.lower()

        # If goal is specified and current tab already matches goal (e.g. goal="instagram" and tab="Instagram"),
        # we don't need a new tab
        if goal and goal.lower() in win_lower:
            return None

        if not is_clean_tab and (active_window or active_tab_title):
            display_title = active_tab_title or active_window.replace("- Google Chrome", "").strip()
            return ContextReport(
                state=ScreenState.CHROME_OCCUPIED_TAB,
                situation=f"Chrome tab is currently occupied with '{display_title}'.",
                utterance=f"Something is already present in this Chrome tab ('{display_title}'), so I'll create a new tab.",
                recommendation=ActionRecommendation(
                    action_type="hotkey",
                    hotkey=["ctrl", "t"],
                    target_id=new_tab_btn_id,
                    explanation="Creating a fresh tab via Ctrl+T so existing work is preserved.",
                ),
                active_window=active_window,
                confidence=0.92,
                metadata={"occupied_title": display_title},
            )

        if is_clean_tab:
            # Address bar ready
            addr_id = None
            for el in elements:
                if el.get("role") in ["Edit", "ComboBox"] and "address" in (el.get("name") or "").lower():
                    addr_id = el.get("id")
                    break

            return ContextReport(
                state=ScreenState.CHROME_NEW_TAB,
                situation="Chrome is on a fresh, clean New Tab.",
                utterance="Chrome is on a clean tab; ready to navigate.",
                recommendation=ActionRecommendation(
                    action_type="click_element" if addr_id else "hotkey",
                    target_id=addr_id,
                    hotkey=["ctrl", "l"] if not addr_id else None,
                    explanation="Focusing address bar for URL entry.",
                ),
                active_window=active_window,
                confidence=0.95,
            )

        return None

    def _check_instagram_flow(
        self, active_window: str, elements: List[Dict[str, Any]], goal: Optional[str]
    ) -> Optional[ContextReport]:
        """Detect Instagram authentication states and recommend the next atomic step."""
        win_lower = active_window.lower()
        page_has_instagram = "instagram" in win_lower or any(
            "instagram" in (el.get("name") or "").lower() for el in elements
        )

        if not page_has_instagram:
            return None

        # Check for Autofill dropdown
        autofill_account = None
        for el in elements:
            name = (el.get("name") or "")
            role = el.get("role", "")
            if role in ["ListItem", "Button"] and ("@" in name or "user" in name.lower() or "arpita" in name.lower() or "shreyash" in name.lower()):
                autofill_account = el
                break

        if autofill_account:
            acc_name = autofill_account.get("name")
            return ContextReport(
                state=ScreenState.INSTAGRAM_AUTOFILL_AVAILABLE,
                situation=f"Instagram login form with saved credentials for '{acc_name}' detected.",
                utterance=f"I see saved login credentials for '{acc_name}', so I'll select it to autofill.",
                recommendation=ActionRecommendation(
                    action_type="click_element",
                    target_id=autofill_account.get("id"),
                    explanation=f"Clicking saved account '{acc_name}' to autofill username and password.",
                ),
                active_window=active_window,
                confidence=0.98,
                metadata={"account": acc_name},
            )

        # Check for login inputs
        user_field = None
        pass_field = None
        login_btn = None
        for el in elements:
            role = el.get("role")
            name_lower = (el.get("name") or "").lower()
            if role == "Edit" and ("mobile" in name_lower or "username" in name_lower or "email" in name_lower):
                user_field = el
            elif role == "Edit" and "password" in name_lower:
                pass_field = el
            elif role == "Button" and "log in" in name_lower and "facebook" not in name_lower:
                login_btn = el

        if user_field:
            return ContextReport(
                state=ScreenState.INSTAGRAM_LOGIN_FORM,
                situation="Instagram login page is displayed with empty credentials fields.",
                utterance="Instagram login form detected. I'll click the username field to input credentials or trigger autofill.",
                recommendation=ActionRecommendation(
                    action_type="click_element",
                    target_id=user_field.get("id"),
                    explanation="Clicking username field to activate input or trigger Chrome saved passwords.",
                ),
                active_window=active_window,
                confidence=0.95,
            )

        # Check for logged-in indicators
        for el in elements:
            name_lower = (el.get("name") or "").lower()
            if any(term in name_lower for term in ["home", "search", "explore", "messages", "notifications", "create", "profile"]):
                if el.get("role") in ["Button", "Hyperlink", "TabItem"]:
                    return ContextReport(
                        state=ScreenState.INSTAGRAM_LOGGED_IN,
                        situation="Instagram authenticated interface (home/messages) is visible.",
                        utterance="Successfully authenticated into Instagram; home dashboard is active.",
                        recommendation=ActionRecommendation(
                            action_type="none",
                            explanation="Authentication verified; task accomplished.",
                        ),
                        active_window=active_window,
                        confidence=0.95,
                    )

        return None

    def _check_dialog_popup(
        self, active_window: str, elements: List[Dict[str, Any]]
    ) -> Optional[ContextReport]:
        """Detect modal dialogs, cookie consent banners, or Chrome restore prompts."""
        for el in elements:
            name = (el.get("name") or "")
            name_lower = name.lower()
            role = el.get("role", "")
            if role in ["Dialog", "Window", "Pane"] and any(
                p in name_lower for p in ["restore pages", "cookies", "allow notifications", "translate"]
            ):
                close_btn_id = None
                for child in elements:
                    child_name = (child.get("name") or "").lower()
                    if child.get("role") == "Button" and any(k in child_name for k in ["close", "cancel", "dismiss", "x"]):
                        close_btn_id = child.get("id")
                        break

                return ContextReport(
                    state=ScreenState.DIALOG_POPUP,
                    situation=f"Modal dialog '{name}' appeared on screen.",
                    utterance=f"A dialog popup ('{name}') appeared. I'll dismiss it so we can continue.",
                    recommendation=ActionRecommendation(
                        action_type="click_element" if close_btn_id else "hotkey",
                        target_id=close_btn_id,
                        hotkey=["esc"] if not close_btn_id else None,
                        explanation="Dismissing popup dialog.",
                    ),
                    active_window=active_window,
                    confidence=0.9,
                    metadata={"dialog_name": name},
                )

        return None
