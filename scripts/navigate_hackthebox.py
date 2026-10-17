"""Automation script: Open Chrome tab and navigate to Hack The Box website.

Follows the Atomic Step Task Planner and Observe -> Contextualize -> Reason -> Act -> Verify loop.
Demonstrates granular burst timing metrics from StepTimer across perception steps.
"""

import os
import sys
import time

# Ensure workspace root is in sys.path
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from ai_controller import DesktopAgentController


def run_hackthebox_navigation():
    desktop = DesktopAgentController()

    print("=" * 70)
    print("TASK: Open Chrome Tab & Navigate to Hack The Box (hackthebox.com)")
    print("=" * 70)

    with desktop.task("navigate_hackthebox"):
        # -------------------------------------------------------------
        # STEP 1: Focus Google Chrome window or launch it
        # -------------------------------------------------------------
        print("\n[Step 1] Finding and focusing Google Chrome...")
        windows = desktop.windows()
        chrome_windows = [
            w for w in windows["windows"]
            if "chrome" in w.get("title", "").lower() or "google chrome" in w.get("title", "").lower()
        ]

        if chrome_windows:
            chrome_title = chrome_windows[0]["title"]
            print(f" -> Found active Chrome window: '{chrome_title}'")
            focused = desktop.focus("Google Chrome")
            print(f" -> Focused Google Chrome: {focused}")
            time.sleep(0.5)
        else:
            print(" -> Chrome not detected in active windows. Launching Google Chrome...")
            desktop.hotkey("win", "r")
            time.sleep(0.5)
            desktop.type_text("chrome", profile="fast")
            time.sleep(0.2)
            desktop.press_key("enter")
            time.sleep(2.0)
            desktop.focus("Google Chrome")

        # -------------------------------------------------------------
        # STEP 2: Observe initial screen and measure step burst times
        # -------------------------------------------------------------
        print("\n[Step 2] Observing screen state (Running multimodal perception pipeline)...")
        t_start_step2 = time.perf_counter()
        obs = desktop.observe(annotate=True, mode="balanced")
        step2_burst_ms = round((time.perf_counter() - t_start_step2) * 1000.0, 2)

        print(f" -> Active Window: '{obs.get('active_window')}'")
        print(f" -> Total Detected UI Elements: {len(obs.get('elements', []))}")
        print(" -> Per-Step Perception Burst Times (ms):")
        timings = obs.get("timings", {})
        for k, v in timings.items():
            if "burst" in k:
                print(f"      * {k:22s} : {v:.2f} ms")
        print(f" -> Step 2 Total Burst Time   : {step2_burst_ms:.2f} ms")

        # -------------------------------------------------------------
        # STEP 3: Contextualize situation (Profile Picker / Occupied Tab)
        # -------------------------------------------------------------
        print("\n[Step 3] Analyzing context & situational awareness...")
        context_report = desktop.analyze_context(observation=obs, goal="hackthebox")
        print(f" -> Screen State : {context_report.state.value}")
        print(f" -> Situation    : {context_report.situation}")
        print(f" -> Utterance    : {context_report.utterance}")
        print(f" -> Recommended  : {context_report.recommendation.action_type} - {context_report.recommendation.explanation}")

        # If profile picker is open, select profile
        if context_report.state.value == "chrome_profile_picker":
            print(" -> Resolving profile picker...")
            if context_report.recommendation.target_id:
                desktop.click_element(context_report.recommendation.target_id)
            else:
                desktop.press_key("enter")
            time.sleep(1.0)
            obs = desktop.observe(annotate=True, mode="fast")

        # -------------------------------------------------------------
        # STEP 4: Open a new Chrome Tab (Ctrl + T)
        # -------------------------------------------------------------
        print("\n[Step 4] Opening a fresh Chrome tab (Ctrl+T)...")
        t_start_step4 = time.perf_counter()
        desktop.hotkey("ctrl", "t")
        time.sleep(0.6)
        step4_burst_ms = round((time.perf_counter() - t_start_step4) * 1000.0, 2)
        print(f" -> Ctrl+T sent. Step 4 Burst Time: {step4_burst_ms:.2f} ms")

        # -------------------------------------------------------------
        # STEP 5: Focus address bar and type target URL
        # -------------------------------------------------------------
        target_url = "https://www.hackthebox.com"
        print(f"\n[Step 5] Focusing address bar (Ctrl+L) and navigating to {target_url}...")
        t_start_step5 = time.perf_counter()
        desktop.hotkey("ctrl", "l")
        time.sleep(0.2)
        desktop.type_text(target_url, profile="natural")
        time.sleep(0.1)
        desktop.press_key("enter")
        step5_burst_ms = round((time.perf_counter() - t_start_step5) * 1000.0, 2)
        print(f" -> URL entered & submitted. Step 5 Burst Time: {step5_burst_ms:.2f} ms")

        # -------------------------------------------------------------
        # STEP 6: Wait for navigation and verify post-condition
        # -------------------------------------------------------------
        print("\n[Step 6] Verifying navigation post-condition...")
        t_start_step6 = time.perf_counter()
        time.sleep(3.0)  # Allow initial page load to begin

        # Wait for page title or visual text
        verified = False
        post_obs = None
        for attempt in range(1, 4):
            print(f" -> Verification attempt {attempt}/3...")
            post_obs = desktop.observe(annotate=True, mode="balanced")
            win_title = post_obs.get("active_window", "")
            print(f"    Current Active Window: '{win_title}'")
            print("    Perception Burst Times for Verification:")
            for k, v in post_obs.get("timings", {}).items():
                if "burst" in k:
                    print(f"      * {k:22s} : {v:.2f} ms")

            # Check window title
            if "hack the box" in win_title.lower() or "hackthebox" in win_title.lower():
                verified = True
                print("    [MATCH] Window title contains 'Hack The Box'!")
                break

            # Check OCR elements
            elements = post_obs.get("elements", [])
            matches = [
                el for el in elements
                if any(kw in (el.get("name") or "").lower() for kw in ["hack the box", "hackthebox", "htb", "cybersecurity"])
            ]
            if matches:
                verified = True
                print(f"    [MATCH] Found {len(matches)} matching UI elements for Hack The Box (e.g. '{matches[0].get('name')}')")
                break

            time.sleep(2.0)

        step6_burst_ms = round((time.perf_counter() - t_start_step6) * 1000.0, 2)
        print(f" -> Step 6 Verification Total Burst Time: {step6_burst_ms:.2f} ms")

        print("\n" + "=" * 70)
        if verified:
            print("[SUCCESS] Successfully navigated to Hack The Box in Google Chrome!")
            if post_obs and post_obs.get("annotated_image_path"):
                print(f"Visual Evidence (Annotated screenshot): {post_obs.get('annotated_image_path')}")
        else:
            print("[PARTIAL] Navigation sent, current window:", post_obs.get("active_window") if post_obs else "Unknown")
        print("=" * 70)

    return 0


if __name__ == "__main__":
    sys.exit(run_hackthebox_navigation())
