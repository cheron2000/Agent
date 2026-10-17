"""Windows UI Automation (UIA) accessibility tree element source."""

import logging
import time
from typing import List, Optional
import win32gui

try:
    from .schema import UIElement
except ImportError:
    from schema import UIElement


logger = logging.getLogger("eyes.uia")


def get_foreground_hwnd() -> Optional[int]:
    """Retrieve HWND of the current active foreground window."""
    try:
        hwnd = win32gui.GetForegroundWindow()
        if hwnd and win32gui.IsWindow(hwnd) and win32gui.IsWindowVisible(hwnd):
            return int(hwnd)
    except Exception:
        pass
    return None


def extract_uia_elements(
    hwnd: Optional[int] = None,
    max_elements: int = 150,
    time_budget_s: float = 1.5,
) -> List[UIElement]:
    """Extract accessible UI elements from the foreground window via UI Automation.
    
    Uses pywinauto.uia_element_info.UIAElementInfo with bounded time and depth.
    Falls back gracefully to uiautomation or returns empty list if UIA is unsupported.
    """
    target_hwnd = hwnd or get_foreground_hwnd()
    elements: List[UIElement] = []

    # 1. Primary path: pywinauto UIAElementInfo
    try:
        from pywinauto.uia_element_info import UIAElementInfo

        root = UIAElementInfo(target_hwnd) if target_hwnd else UIAElementInfo()
        t0 = time.monotonic()
        descendant_iter = getattr(root, "iter_descendants", None)
        descendants = descendant_iter() if descendant_iter else getattr(root, "children", list)()

        for info in descendants:
            if time.monotonic() - t0 > time_budget_s or len(elements) >= max_elements:
                break
            try:
                if not getattr(info, "visible", True):
                    continue
                r = info.rectangle
                w = r.right - r.left
                h = r.bottom - r.top
                if w < 4 or h < 4:
                    continue

                name = (getattr(info, "name", "") or "").strip()
                role = str(getattr(info, "control_type", "Control") or "Control")
                enabled = bool(getattr(info, "enabled", True))

                # Skip completely blank nameless non-interactive panels to keep output dense
                if not name and role in {"Pane", "Group", "Window", "Custom"}:
                    continue

                elements.append(
                    UIElement(
                        id=0,  # Will be assigned by observe.py
                        role=role,
                        name=name,
                        box=[int(r.left), int(r.top), int(r.right), int(r.bottom)],
                        enabled=enabled,
                        source="uia",
                        conf=1.0,
                    )
                )
            except Exception:
                continue

        if elements:
            return elements
    except Exception as e:
        logger.debug("pywinauto UIA extraction skipped or failed: %s", e)

    # 2. Fallback path: uiautomation package
    try:
        import uiautomation as auto

        ctrl = auto.ControlFromHandle(target_hwnd) if target_hwnd else auto.GetRootControl()
        t0 = time.monotonic()
        for c, _ in auto.WalkTree(ctrl, maxDepth=4):
            if time.monotonic() - t0 > time_budget_s or len(elements) >= max_elements:
                break
            try:
                r = c.BoundingRectangle
                w = r.right - r.left
                h = r.bottom - r.top
                if w < 4 or h < 4:
                    continue
                name = (c.Name or "").strip()
                role = c.ControlTypeName or "Control"
                if not name and role in {"PaneControl", "GroupControl", "WindowControl"}:
                    continue

                elements.append(
                    UIElement(
                        id=0,
                        role=role.replace("Control", ""),
                        name=name,
                        box=[int(r.left), int(r.top), int(r.right), int(r.bottom)],
                        enabled=bool(c.IsEnabled),
                        source="uia",
                        conf=1.0,
                    )
                )
            except Exception:
                continue
    except Exception as e:
        logger.debug("uiautomation fallback failed: %s", e)

    return elements
