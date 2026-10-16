"""parallel_canvas.py - Parallel AI Desktop Canvas using Isolated Chromium & Visual AI Cursor.

Architecture:
- Parallel execution: Runs simultaneously alongside your personal desktop without stealing your physical mouse or screen focus.
- Visual AI Cursor: Glowing neon cyan pointer glides across elements and renders click ripple animations so you see the AI operating in real time.
- Strict Spatial Scoping: Screenshots and OCR transcriptions happen strictly inside the canvas viewport.
- Ephemeral Lifecycle: All screenshots captured during a task are automatically deleted when the task completes.
"""

import os
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

from playwright.sync_api import BrowserContext, Page, Playwright, sync_playwright

# Ensure Eyes is importable for OCR and ephemeral task management
sys.path.append(os.path.join(os.path.dirname(__file__), "Eyes"))
import eyes

CURSOR_INJECTION_JS = """
(() => {
    // Inject animation and HUD styles
    if (!document.getElementById('ai-cursor-styles')) {
        const style = document.createElement('style');
        style.id = 'ai-cursor-styles';
        style.textContent = `
            @keyframes aiRipplePulse {
                0% { transform: scale(0.4); opacity: 1; }
                100% { transform: scale(2.4); opacity: 0; }
            }
            .ai-cursor-ripple {
                position: fixed;
                width: 32px;
                height: 32px;
                margin-left: -16px;
                margin-top: -16px;
                border-radius: 50%;
                border: 2px solid #00d2ff;
                box-shadow: 0 0 12px #00d2ff, inset 0 0 8px #00d2ff;
                pointer-events: none !important;
                z-index: 2147483647 !important;
                animation: aiRipplePulse 0.45s ease-out forwards;
            }
            #ai-desktop-pointer {
                position: fixed;
                width: 24px;
                height: 24px;
                pointer-events: none !important;
                z-index: 2147483647 !important;
                transition: left 0.28s cubic-bezier(0.25, 1, 0.5, 1), top 0.28s cubic-bezier(0.25, 1, 0.5, 1);
                filter: drop-shadow(0 2px 6px rgba(0, 210, 255, 0.7));
            }
            #ai-desktop-hud {
                position: fixed;
                top: 8px;
                left: 50%;
                transform: translateX(-50%);
                background: rgba(15, 23, 42, 0.94);
                border: 1px solid rgba(0, 210, 255, 0.5);
                box-shadow: 0 4px 16px rgba(0, 0, 0, 0.6), 0 0 10px rgba(0, 210, 255, 0.3);
                border-radius: 20px;
                padding: 4px 16px;
                display: flex;
                align-items: center;
                gap: 12px;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                font-size: 11px;
                color: #e2e8f0;
                pointer-events: none !important;
                z-index: 2147483646 !important;
            }
            .hud-badge {
                color: #00d2ff;
                font-weight: 700;
                display: flex;
                align-items: center;
                gap: 6px;
            }
            .hud-dot {
                width: 7px;
                height: 7px;
                background: #00d2ff;
                border-radius: 50%;
                box-shadow: 0 0 6px #00d2ff;
            }
            .hud-status {
                color: #f8fafc;
                font-weight: 500;
            }
            .hud-tag {
                color: #10b981;
                font-weight: 600;
                border-left: 1px solid rgba(255, 255, 255, 0.2);
                padding-left: 8px;
            }
        `;
        document.documentElement.appendChild(style);
    }

    // Inject visual cursor pointer and HUD
    function ensureCursorAndHud() {
        if (!document.getElementById('ai-desktop-pointer')) {
            const ptr = document.createElement('div');
            ptr.id = 'ai-desktop-pointer';
            ptr.innerHTML = `
                <svg width="22" height="22" viewBox="0 0 24 24" fill="none">
                    <path d="M4 3L11 21L14.5 13.5L22 10L4 3Z" fill="#00d2ff" stroke="#ffffff" stroke-width="1.8" stroke-linejoin="round"/>
                </svg>
            `;
            ptr.style.left = '50px';
            ptr.style.top = '50px';
            document.documentElement.appendChild(ptr);
        }
        if (!document.getElementById('ai-desktop-hud')) {
            const hud = document.createElement('div');
            hud.id = 'ai-desktop-hud';
            hud.innerHTML = `
                <div class="hud-badge"><div class="hud-dot"></div>DESKTOP 2 [AI CANVAS]</div>
                <div class="hud-status" id="ai-hud-status">AI Idle - Ready</div>
                <div class="hud-tag">ISOLATION: 100% CANVAS BOUNDED</div>
            `;
            document.documentElement.appendChild(hud);
        }
    }

    ensureCursorAndHud();

    window.__aiMoveCursor = (x, y) => {
        ensureCursorAndHud();
        const ptr = document.getElementById('ai-desktop-pointer');
        if (ptr) {
            ptr.style.left = x + 'px';
            ptr.style.top = y + 'px';
        }
    };

    window.__aiTriggerRipple = (x, y) => {
        const rip = document.createElement('div');
        rip.className = 'ai-cursor-ripple';
        rip.style.left = x + 'px';
        rip.style.top = y + 'px';
        document.documentElement.appendChild(rip);
        setTimeout(() => rip.remove(), 500);
    };

    window.__aiSetStatus = (msg) => {
        ensureCursorAndHud();
        const el = document.getElementById('ai-hud-status');
        if (el) el.textContent = msg;
    };
})();
"""



class ParallelCanvasDesktop:
    """Parallel AI Desktop Canvas running in an isolated Chromium process."""

    def __init__(
        self,
        profile_dir: Optional[str] = None,
        width: int = 1240,
        height: int = 800,
    ):
        self.profile_dir = profile_dir or os.path.abspath(
            os.path.join(os.path.dirname(__file__), "ai_chrome_profile")
        )
        os.makedirs(self.profile_dir, exist_ok=True)

        self.width = width
        self.height = height
        self._pw: Optional[Playwright] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.cursor_pos: Tuple[int, int] = (100, 100)

    def _spawn_visible_chrome(self, url: str, port: int = 9222) -> bool:
        """Launch Chrome on interactive desktop (WinSta0\\Default) so it is visible to the user."""
        try:
            import ctypes
            from ctypes import wintypes
            import requests

            # If already running on port, don't spawn a second instance
            try:
                r = requests.get(f"http://127.0.0.1:{port}/json/version", timeout=0.8)
                if r.status_code == 200:
                    return True
            except Exception:
                pass

            class STARTUPINFO(ctypes.Structure):
                _fields_ = [
                    ('cb', wintypes.DWORD),
                    ('lpReserved', wintypes.LPWSTR),
                    ('lpDesktop', wintypes.LPWSTR),
                    ('lpTitle', wintypes.LPWSTR),
                    ('dwX', wintypes.DWORD),
                    ('dwY', wintypes.DWORD),
                    ('dwXSize', wintypes.DWORD),
                    ('dwYSize', wintypes.DWORD),
                    ('dwXCountChars', wintypes.DWORD),
                    ('dwYCountChars', wintypes.DWORD),
                    ('dwFillAttribute', wintypes.DWORD),
                    ('dwFlags', wintypes.DWORD),
                    ('wShowWindow', wintypes.WORD),
                    ('cbReserved2', wintypes.WORD),
                    ('lpReserved2', ctypes.c_void_p),
                    ('hStdInput', wintypes.HANDLE),
                    ('hStdOutput', wintypes.HANDLE),
                    ('hStdError', wintypes.HANDLE),
                ]

            class PROCESS_INFORMATION(ctypes.Structure):
                _fields_ = [
                    ('hProcess', wintypes.HANDLE),
                    ('hThread', wintypes.HANDLE),
                    ('dwProcessId', wintypes.DWORD),
                    ('dwThreadId', wintypes.DWORD),
                ]

            chrome_exe = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
            cmd = (
                f'"{chrome_exe}" '
                f'--remote-debugging-port={port} '
                f'--user-data-dir="{self.profile_dir}" '
                f'--window-size={self.width + 16},{self.height + 64} '
                f'--window-position=50,50 '
                f'--no-first-run '
                f'--no-default-browser-check '
                f'--app="{url}"'
            )

            si = STARTUPINFO()
            si.cb = ctypes.sizeof(STARTUPINFO)
            si.lpDesktop = "WinSta0\\Default"

            pi = PROCESS_INFORMATION()
            ok = ctypes.windll.kernel32.CreateProcessW(
                None, cmd, None, None, False, 0, None, None, ctypes.byref(si), ctypes.byref(pi)
            )
            if not ok:
                return False

            # Wait for CDP port to open
            for _ in range(12):
                time.sleep(0.5)
                try:
                    r = requests.get(f"http://127.0.0.1:{port}/json/version", timeout=0.5)
                    if r.status_code == 200:
                        return True
                except Exception:
                    pass
            return False
        except Exception:
            return False

    def start(self, initial_url: Optional[str] = None):
        """Launch the parallel desktop window with visual cursor and persistent profile."""
        if not initial_url:
            home_file = os.path.abspath(os.path.join(os.path.dirname(__file__), "desktop_home.html"))
            initial_url = f"file:///{home_file.replace(os.sep, '/')}"

        self._pw = sync_playwright().start()

        # Try visible interactive launch on user desktop first
        spawned = self._spawn_visible_chrome(initial_url)
        if spawned:
            try:
                browser = self._pw.chromium.connect_over_cdp("http://127.0.0.1:9222")
                self.context = browser.contexts[0]
                self.page = self.context.pages[0] if self.context.pages else self.context.new_page()
                print(f"[Parallel Canvas] [VISIBLE LAUNCH] Attached to visible user desktop window at: {initial_url}")
            except Exception as e:
                print(f"[Parallel Canvas] CDP attach fallback: {e}")
                self.context = None

        # Fallback to persistent context launch if CDP was not used
        if not self.context:
            self.context = self._pw.chromium.launch_persistent_context(
                user_data_dir=self.profile_dir,
                headless=False,
                channel="chrome",
                viewport={"width": self.width, "height": self.height},
                args=[
                    f"--window-size={self.width + 16},{self.height + 64}",
                    "--window-position=40,40",
                    "--app=" + initial_url,
                    "--disable-blink-features=AutomationControlled",
                ],
                ignore_default_args=["--enable-automation"],
            )
            self.page = self.context.pages[0] if self.context.pages else self.context.new_page()
            self.page.goto(initial_url, wait_until="domcontentloaded")
            print(f"[Parallel Canvas] [PERSISTENT LAUNCH] Launched parallel desktop window at: {initial_url}")

        self.context.add_init_script(CURSOR_INJECTION_JS)
        self._ensure_cursor_script()


    def set_status(self, status: str):
        """Update floating HUD status on the canvas in real time."""
        if not self.page:
            return
        try:
            clean = status.replace("'", "\\'").replace('"', '\\"')
            self.page.evaluate(f"window.__aiSetStatus('{clean}')")
        except Exception:
            pass


    def _ensure_cursor_script(self):
        try:
            self.page.evaluate(CURSOR_INJECTION_JS)
        except Exception:
            pass

    def navigate(self, url: str):
        """Navigate to URL inside the parallel canvas."""
        if self.page:
            self.page.goto(url, wait_until="domcontentloaded")
            time.sleep(1.0)
            self._ensure_cursor_script()

    def move_mouse(self, x: int, y: int, duration: float = 0.3):
        """Glide the visual AI cursor smoothly to (x, y) without moving the user's physical mouse."""
        if not self.page:
            return
        self.cursor_pos = (x, y)
        try:
            self.page.evaluate(f"window.__aiMoveCursor({x}, {y})")
        except Exception:
            self._ensure_cursor_script()
            try:
                self.page.evaluate(f"window.__aiMoveCursor({x}, {y})")
            except Exception:
                pass
        self.page.mouse.move(x, y)
        time.sleep(duration)

    def click(self, x: int, y: int, button: str = "left"):
        """Perform a virtual click inside the canvas with visual ripple effect."""
        if not self.page:
            return
        self.move_mouse(x, y, duration=0.25)
        try:
            self.page.evaluate(f"window.__aiTriggerRipple({x}, {y})")
        except Exception:
            pass
        self.page.mouse.click(x, y, button=button)
        time.sleep(0.3)

    def type_text(self, text: str, delay: float = 0.04):
        """Type text with realistic keystrokes into the active canvas input."""
        if not self.page:
            return
        self.page.keyboard.type(text, delay=int(delay * 1000))

    def press_key(self, key: str):
        """Press a keyboard key inside the canvas."""
        if not self.page:
            return
        self.page.keyboard.press(key)

    def scroll(self, delta_y: int):
        """Scroll mouse wheel smoothly inside the canvas."""
        if not self.page:
            return
        self.page.mouse.wheel(0, delta_y)
        time.sleep(0.5)

    def capture(self, save: bool = True) -> Dict[str, Any]:
        """Capture screenshot strictly from the canvas viewport and register with ephemeral session."""
        if not self.page:
            return {"success": False, "path": None, "error": "Page not loaded"}

        shots_dir = eyes.SHOTS_DIR
        ts = time.strftime("%Y%m%d_%H%M%S")
        path = str(shots_dir / f"canvas_screen_{ts}.png")

        self.page.screenshot(path=path)

        # Register with active task session for auto-cleanup
        if eyes._ACTIVE_TASK_SESSION:
            eyes._ACTIVE_TASK_SESSION.add_screenshot(path)

        return {
            "success": True,
            "path": path,
            "width": self.width,
            "height": self.height,
            "error": None,
        }

    def transcribe(self, detailed: bool = False) -> Dict[str, Any]:
        """Run OCR strictly on the canvas viewport image."""
        cap = self.capture(save=True)
        if not cap["success"]:
            return {"success": False, "text": "", "elements": []}

        try:
            import pytesseract
            from PIL import Image

            tess = eyes._find_tesseract()
            if tess:
                pytesseract.pytesseract.tesseract_cmd = tess

            img = Image.open(cap["path"])
            if not detailed:
                text = pytesseract.image_to_string(img).strip()
                return {"success": True, "text": text, "elements": []}

            data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
            elements = []
            full_parts = []
            n = len(data["text"])
            for i in range(n):
                w = data["text"][i].strip()
                c = int(data["conf"][i])
                if w and c > 25:
                    x = data["left"][i]
                    y = data["top"][i]
                    bw = data["width"][i]
                    bh = data["height"][i]
                    full_parts.append(w)
                    elements.append({
                        "text": w,
                        "confidence": c,
                        "center": {"x": x + bw // 2, "y": y + bh // 2},
                        "box": {"x": x, "y": y, "width": bw, "height": bh},
                    })

            return {"success": True, "text": " ".join(full_parts), "elements": elements}
        except Exception as e:
            return {"success": False, "text": "", "elements": [], "error": str(e)}

    def find_on_canvas(self, target: str) -> Dict[str, Any]:
        """Find an element on the canvas by text with exact pixel coordinates."""
        ocr = self.transcribe(detailed=True)
        target_clean = target.strip().lower()
        matches = []
        for el in ocr.get("elements", []):
            if target_clean in el["text"].lower():
                matches.append(el)

        if matches:
            best = max(matches, key=lambda m: m["confidence"])
            return {
                "found": True,
                "x": best["center"]["x"],
                "y": best["center"]["y"],
                "text": best["text"],
                "box": best["box"],
            }
        return {"found": False, "x": None, "y": None}

    def close(self):
        """Close parallel canvas context."""
        try:
            if self.context:
                self.context.close()
            if self._pw:
                self._pw.stop()
        except Exception:
            pass
