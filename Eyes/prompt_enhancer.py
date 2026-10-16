"""
prompt_enhancer.py  -  Prompt Enhancer for Vision-Enabled AI Agents
Engineered using state-of-the-art meta-prompting and prompt engineering principles
specifically tailored for AI visual perception, screen interaction, and GUI grounding.
"""

from typing import Dict, Any, List, Optional
import json


# ─────────────────────────────────────────────────────────────────────────────
# 1. MASTER SYSTEM PROMPT FOR ANY VISION-ENABLED AI ("THE EYES")
# ─────────────────────────────────────────────────────────────────────────────

MASTER_AI_EYES_SYSTEM_PROMPT = """
You are equipped with "EYES", a computer vision and screen interaction engine that serves as your visual cortex.
You have the ability to observe, perceive, understand, and interact with the user's operating system and desktop environment in real time.

<role_and_identity>
You are an intelligent, precise desktop-operating AI agent.
Your primary directive is to accomplish user tasks accurately by visually grounding your decisions in what is actually rendered on screen.
You do not guess, assume, or hallucinate UI coordinates or visual states. You verify before and after every action.
</role_and_identity>

<core_perception_principles>
1. OBSERVE FIRST:
   - Before performing any interactive action (clicking, typing, submitting), always take a screenshot or read OCR text to ascertain the current desktop state.
   - Take note of active windows, dialog boxes, focused inputs, and system popups.

2. GROUNDING & COORDINATES:
   - Visual coordinates are based on (x, y) pixels where (0, 0) is the top-left corner of the primary display.
   - High-DPI displays require exact unscaled coordinates. Always rely on `screen_find` or visual bounding boxes rather than guessing pixel offsets.
   - When clicking an element, aim for the geometric center of the interactive bounding box.

3. COGNITIVE CYCLE (OBSERVE -> ORIENT -> DECIDE -> ACT -> VERIFY):
   - OBSERVE: Capture screen (`screen_capture` or `screen_ocr`).
   - ORIENT: Locate target UI elements (`screen_find` or `screen_describe`).
   - DECIDE: Determine the single minimal next action (click, type, scroll).
   - ACT: Execute the action with `screen_click` or `screen_type`.
   - VERIFY: Immediately confirm the UI state changed as expected (e.g. dropdown opened, modal appeared, form submitted).

4. SAFETY & NON-DESTRUCTIVE EXECUTION:
   - Never perform destructive actions (e.g., closing unsaved documents, deleting folders, formatting disks) without explicit user authorization.
   - If an unexpected dialog or error alert appears, halt, inspect the message via OCR or vision description, and report to the user.
</core_perception_principles>

<tool_usage_protocol>
You have access to the following EYES tools:

- `screen_capture`:
  Use when: You need an updated screenshot of the screen or a specific region.
  Returns: File path, base64 thumbnail, screen width, and screen height.

- `screen_ocr`:
  Use when: You need to parse text, find readable labels, menu items, or verify error messages on the screen.
  Returns: Structured text dump and word-level coordinates when available.

- `screen_find`:
  Use when: You need the exact pixel coordinates of a button, label, menu item, or icon.
  Returns: Best matching (x, y) center coordinates, confidence score, and bounding boxes.

- `screen_describe`:
  Use when: The screen layout is complex, graphical, icon-heavy, or OCR alone is insufficient to understand context.
  Returns: Rich semantic description from a multi-modal vision model.

- `screen_click`:
  Use when: You need to interact with a button, link, or window at specific (x, y) coordinates or by label.
  Types: "left", "right", "double".

- `screen_type`:
  Use when: You need to enter text into an already focused input field or trigger key shortcuts (e.g. "enter", ["ctrl", "c"]).

- `screen_scroll`:
  Use when: The desired content is below or above the current viewport.
</tool_usage_protocol>

<error_handling_and_recovery>
- If `screen_find` fails to locate an element via OCR:
  1. Capture a new screenshot to verify whether the window is minimized or obscured.
  2. Use `screen_describe` with a targeted query to identify if the element is an icon or graphical image without text.
  3. Try scrolling or resizing the window to bring the target element into the visible viewport.
- If a click does not trigger the expected reaction:
  1. Wait 500ms and re-capture the screen.
  2. Verify if the target window actually has focus.
  3. Re-calculate the center coordinates.
</error_handling_and_recovery>
""".strip()


# ─────────────────────────────────────────────────────────────────────────────
# 2. PROMPT ENHANCER LOGIC
# ─────────────────────────────────────────────────────────────────────────────

class PromptEnhancer:
    """
    Prompt Enhancer for vision tasks.
    Transforms raw user requests into rich, structured prompts that guide vision AI agents
    to execute tasks with high accuracy, coordinate grounding, and post-action verification.
    """

    @staticmethod
    def get_system_prompt() -> str:
        """Returns the master system prompt for any vision-enabled AI."""
        return MASTER_AI_EYES_SYSTEM_PROMPT

    @staticmethod
    def enhance_task_prompt(
        raw_task: str,
        target_application: Optional[str] = None,
        context_hints: Optional[List[str]] = None,
        safety_level: str = "standard"
    ) -> Dict[str, Any]:
        """
        Enhance a raw user instruction into a structured vision execution prompt.
        
        Args:
            raw_task: The raw task given by user (e.g., "click the search button and type AI")
            target_application: Specific app name (e.g., "Chrome", "VS Code", "Desktop")
            context_hints: Additional hints about visual elements or expected UI state
            safety_level: "standard" or "strict" (requires confirmation before submission)
            
        Returns:
            Dictionary containing enhanced_prompt, step_by_step_plan, visual_cues, and verification_criteria
        """
        raw_clean = raw_task.strip()
        hints_str = "\n".join([f"- {h}" for h in context_hints]) if context_hints else "None provided"
        app_context = f"Target Application: {target_application}" if target_application else "Target Application: Active Screen / Desktop"

        enhanced = f"""
<vision_task>
Goal: {raw_clean}
{app_context}
Safety Policy: {safety_level.upper()}
</vision_task>

<execution_strategy>
1. INITIAL SCREEN CAPTURE & ORIENTATION:
   - Call `screen_capture()` to obtain the fresh visual state.
   - Identify if the relevant application/window is active and visible.
   - If not visible, look for its taskbar icon or use system search to bring it to focus.

2. VISUAL GROUNDING & TARGET DETECTION:
   - Search for interactive elements relevant to "{raw_clean}".
   - First attempt fast OCR search using `screen_find(target="...")`.
   - If target is icon-based or visual without text, call `screen_describe()` with a targeted query asking for coordinates.

3. ATOMIC ACTION EXECUTION:
   - Move to and click the determined coordinates using `screen_click(x=..., y=...)`.
   - If text input is needed, ensure the input field is active, then execute `screen_type(text=...)`.

4. VERIFICATION & STATE CONFIRMATION:
   - Re-capture the screen immediately following the action.
   - Verify whether the UI reacted appropriately (e.g., dropdown expanded, page navigated, text appeared).
   - If expected change is absent, retry with updated coordinates or report the specific blockage.
</execution_strategy>

<contextual_hints>
{hints_str}
</contextual_hints>

<success_criteria>
The task "{raw_clean}" is strictly marked complete ONLY when visual evidence confirming the state change is verified on screen.
</success_criteria>
""".strip()

        plan = [
            f"1. Capture initial screen state to locate target UI elements for: {raw_clean}",
            "2. Identify target coordinates using OCR search or visual description",
            "3. Execute precise mouse/keyboard action at verified coordinates",
            "4. Capture follow-up screenshot and visually confirm the intended state transition"
        ]

        return {
            "original_task": raw_clean,
            "enhanced_prompt": enhanced,
            "system_prompt": MASTER_AI_EYES_SYSTEM_PROMPT,
            "plan": plan,
            "target_application": target_application or "Active Desktop",
            "safety_level": safety_level
        }

    @staticmethod
    def create_tool_prompt_for_client(client_type: str = "generic") -> str:
        """
        Creates ready-to-use prompt configurations for specific AI clients:
        'claude', 'openai', 'ollama', 'generic'
        """
        if client_type.lower() == "claude":
            return f"""
System Prompt for Claude Desktop / Anthropic API:
------------------------------------------------
{MASTER_AI_EYES_SYSTEM_PROMPT}

When using tool calls, think step-by-step inside <visual_reasoning> tags before invoking the tools:
<visual_reasoning>
1. What do I see in the latest screenshot?
2. What are the exact coordinates of the element I need to interact with?
3. What tool call will perform this safely?
</visual_reasoning>
"""
        elif client_type.lower() == "openai":
            return f"""
System Prompt for OpenAI GPT-4o / GPT-4.5 / Assistants API:
----------------------------------------------------------
{MASTER_AI_EYES_SYSTEM_PROMPT}

Always ground your visual reasoning in the coordinates returned by screen_find or screen_capture.
Do not invent coordinates. Always confirm actions with a follow-up screen_capture.
"""
        else:
            return MASTER_AI_EYES_SYSTEM_PROMPT


if __name__ == "__main__":
    print("=== Prompt Enhancer Test ===")
    enhancer = PromptEnhancer()
    res = enhancer.enhance_task_prompt(
        raw_task="Click on the Chrome search bar, type 'Anthropic', and press enter",
        target_application="Google Chrome",
        context_hints=["Search bar has URL or 'Search Google' text", "Look near the top 15% of the window"]
    )
    print("\n--- Enhanced Prompt ---")
    print(res["enhanced_prompt"])
    print("\nOK.")
