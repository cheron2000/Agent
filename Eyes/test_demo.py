"""
test_demo.py  -  Live Demonstration of EYES Vision Engine & Prompt Enhancer
"""

import json
import eyes
from prompt_enhancer import PromptEnhancer

def run_demo():
    print("=" * 60)
    print("  EYES VISION ENGINE & PROMPT ENHANCER - LIVE DEMO")
    print("=" * 60)

    # 1. Screen Info
    print("\n[STEP 1] Querying Screen Resolution & Cursor Position...")
    info = eyes.get_screen_info()
    print(f"  Screen Dimensions: {info['width']} x {info['height']}")
    print(f"  Current Cursor:    ({info['cursor']['x']}, {info['cursor']['y']})")

    # 2. Capture Screen
    print("\n[STEP 2] Capturing Active Screen Screenshot...")
    cap = eyes.capture(save=True)
    if cap["success"]:
        print(f"  Screenshot saved to: {cap['path']}")
        print(f"  Captured Image Size: {cap['width']} x {cap['height']}")
    else:
        print(f"  Capture error: {cap['error']}")

    # 3. Read Screen Text (OCR)
    print("\n[STEP 3] Performing OCR Analysis...")
    ocr = eyes.read_text(detailed=True)
    if ocr["success"]:
        text_sample = ocr["text"].strip()
        print(f"  Total text length: {len(text_sample)} characters")
        print(f"  Extracted Elements: {len(ocr['elements'])} word-level bounding boxes detected")
        if text_sample:
            preview = text_sample[:250].replace("\n", " ")
            print(f"  Screen Text Snippet: \"{preview}...\"")
        
        # 4. Find element
        if ocr["elements"]:
            sample_word = ocr["elements"][0]["text"]
            print(f"\n[STEP 4] Locating Target UI Element '{sample_word}'...")
            found = eyes.find_on_screen(sample_word)
            if found.get("found"):
                print(f"  Found '{sample_word}' at center coordinates: ({found['x']}, {found['y']})")
                print(f"  Confidence: {found['confidence']}%")
                print(f"  Bounding Box: {found['box']}")
    else:
        print(f"  OCR error: {ocr['error']}")

    # 5. Prompt Enhancer
    print("\n[STEP 5] Testing Prompt Enhancer on a Real Task...")
    enhancer = PromptEnhancer()
    user_goal = "Open Google Chrome and search for the latest AI vision models"
    print(f"  Raw User Prompt: \"{user_goal}\"")
    enhanced = enhancer.enhance_task_prompt(
        raw_task=user_goal,
        target_application="Google Chrome",
        context_hints=["Check taskbar icon for Chrome", "URL bar is at the top of the browser"]
    )
    print("\n  --- Enhanced Plan Generated ---")
    for step in enhanced["plan"]:
        print(f"   {step}")

    print("\n" + "=" * 60)
    print("[SUCCESS] DEMO COMPLETE: The EYES system is fully operational!")
    print("=" * 60)

if __name__ == "__main__":
    run_demo()
