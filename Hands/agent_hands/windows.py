"""Windows window detection, focus, and activation management."""

import ctypes
import re
from typing import Dict, List, Optional
import win32con
import win32gui
import win32process


def ensure_interactive_desktop():
    """Ensure the current thread is attached to the interactive desktop (WinSta0\\Default)."""
    try:
        winsta = ctypes.windll.user32.OpenWindowStationW("WinSta0", False, 0x10000000)
        if winsta:
            ctypes.windll.user32.SetProcessWindowStation(winsta)
        desk = ctypes.windll.user32.OpenDesktopW("Default", 0, False, 0x10000000)
        if desk:
            ctypes.windll.user32.SetThreadDesktop(desk)
    except Exception:
        pass


def list_windows() -> List[Dict[str, str]]:
    """List all currently visible, titled windows on the desktop."""
    ensure_interactive_desktop()
    windows: List[Dict[str, str]] = []

    def enum_cb(hwnd: int, _):
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd).strip()
            if title:
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                windows.append({
                    "hwnd": str(hwnd),
                    "title": title,
                    "pid": str(pid),
                })
        return True

    try:
        win32gui.EnumWindows(enum_cb, None)
    except Exception:
        pass

    return windows


def find_window(title_pattern: str) -> Optional[int]:
    """Find the HWND of the first window matching title pattern (substring or regex)."""
    ensure_interactive_desktop()
    pattern = re.compile(title_pattern, re.IGNORECASE)
    matches: List[int] = []

    def enum_cb(hwnd: int, _):
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd).strip()
            if title and pattern.search(title):
                matches.append(hwnd)
        return True

    try:
        win32gui.EnumWindows(enum_cb, None)
    except Exception:
        pass

    return matches[0] if matches else None


def focus_window(title_or_hwnd: str | int) -> bool:
    """Activate and bring the target window to the foreground."""
    ensure_interactive_desktop()
    hwnd = None
    if isinstance(title_or_hwnd, int):
        hwnd = title_or_hwnd
    elif isinstance(title_or_hwnd, str) and title_or_hwnd.isdigit():
        hwnd = int(title_or_hwnd)
    else:
        hwnd = find_window(str(title_or_hwnd))

    if not hwnd or not win32gui.IsWindow(hwnd):
        return False

    # Three-level fallback: full WinAPI -> SwitchToThisWindow only -> SetForegroundWindow
    try:
        # If minimized, restore it
        if win32gui.IsIconic(hwnd):
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        else:
            win32gui.ShowWindow(hwnd, win32con.SW_SHOW)

        # Guarantee foreground activation on Windows 10/11
        ctypes.windll.user32.SwitchToThisWindow(hwnd, True)
        ctypes.windll.user32.SetForegroundWindow(hwnd)
        ctypes.windll.user32.SetFocus(hwnd)
        return True
    except Exception:
        # Level 2: SwitchToThisWindow alone
        try:
            ctypes.windll.user32.SwitchToThisWindow(hwnd, True)
            return True
        except Exception:
            pass

    # Level 3: win32gui fallback
    try:
        win32gui.SetForegroundWindow(hwnd)
        return True
    except Exception:
        return False


def get_active_window_title() -> str:
    """Get the title of the current active/foreground window."""
    ensure_interactive_desktop()
    try:
        hwnd = win32gui.GetForegroundWindow()
        if hwnd:
            return win32gui.GetWindowText(hwnd).strip()
    except Exception:
        pass
    return ""
