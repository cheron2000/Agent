from workflow_runner import WorkflowError, WorkflowRunner, WorkflowStep


class FakeController:
    def __init__(self):
        self.calls = []
        self.text = ""
        self.active_window = "Notepad"
        self.elements = [{"id": 1, "name": "Save"}]
        self.fail_clicks = 0

    def observe(self, **kwargs):
        self.calls.append(("observe", kwargs))
        return {"elements": self.elements}

    def transcribe(self, detailed=False):
        self.calls.append(("transcribe", detailed))
        return {"text": self.text}

    def windows(self):
        self.calls.append(("windows",))
        return {"active_window": self.active_window, "windows": []}

    def click_element(self, element_id, **kwargs):
        self.calls.append(("click_element", element_id))
        if self.fail_clicks:
            self.fail_clicks -= 1
            raise RuntimeError("click failed")
        self.text = "Saved"
        return {"success": True, "element_id": element_id}

    def type_text(self, text, **kwargs):
        self.calls.append(("type_text", text))
        self.text = text
        return {"success": True}

    def paste_text(self, text, **kwargs):
        self.calls.append(("paste_text", text))
        self.text = text

    def press_key(self, key):
        self.calls.append(("press_key", key))

    def hotkey(self, *keys):
        self.calls.append(("hotkey", keys))

    def scroll(self, clicks, **kwargs):
        self.calls.append(("scroll", clicks))
        return {"success": True}

    def focus(self, window_title):
        self.calls.append(("focus", window_title))
        self.active_window = window_title
        return True

    def wait_for_text(self, target, timeout_s=5.0):
        self.calls.append(("wait_for_text", target, timeout_s))
        return {"success": target.casefold() in self.text.casefold(), "text": self.text}


def test_step_clicks_and_verifies_text():
    controller = FakeController()
    runner = WorkflowRunner(controller, sleep=lambda _: None)

    result = runner.run([{
        "intent": "Save the document",
        "action": "click_element",
        "parameters": {"element_id": 1},
        "verification": {"type": "text_contains", "expected": "Saved"},
    }])

    assert result["success"] is True
    assert result["completed_steps"] == 1
    assert controller.calls[:2] == [("click_element", 1), ("wait_for_text", "Saved", 5.0)]


def test_failed_step_retries_and_runs_recovery():
    controller = FakeController()
    controller.fail_clicks = 1
    runner = WorkflowRunner(controller, sleep=lambda _: None)

    result = runner.run([{
        "intent": "Save after recovering",
        "action": "click_element",
        "parameters": {"element_id": 1},
        "retries": 1,
        "recovery": {"action": "press_key", "parameters": {"key": "esc"}},
        "verification": {"type": "text_contains", "expected": "Saved"},
    }])

    assert result["success"] is True
    assert result["results"][0]["attempts"] == 2
    assert ("press_key", "esc") in controller.calls


def test_active_window_and_element_verification():
    controller = FakeController()
    runner = WorkflowRunner(controller, sleep=lambda _: None)

    result = runner.run([
        {
            "intent": "Focus Notepad",
            "action": "focus",
            "parameters": {"window_title": "Notepad"},
            "verification": {"type": "active_window_contains", "expected": "Note"},
        },
        {
            "intent": "Find Save control",
            "action": "wait",
            "parameters": {"seconds": 0},
            "verification": {"type": "element_name_contains", "expected": "Save"},
        },
    ])

    assert result["success"] is True
    assert result["completed_steps"] == 2


def test_verification_is_required():
    runner = WorkflowRunner(FakeController(), sleep=lambda _: None)
    result = runner.run([{"intent": "Missing contract", "action": "wait", "parameters": {"seconds": 0}}])

    assert result["success"] is False
    assert "verification" in result["results"][0]["error"]


def test_unsupported_action_is_reported():
    runner = WorkflowRunner(FakeController(), sleep=lambda _: None)
    result = runner.run([{
        "intent": "Unsupported",
        "action": "teleport",
        "verification": {"type": "text_contains", "expected": "never"},
        "retries": 0,
    }])

    assert result["success"] is False
    assert "Unsupported workflow action" in result["results"][0]["error"]
