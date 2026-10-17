"""Unit tests for the Context reasoning and decision layer."""

import pytest
from Context import ContextAnalyzer, ScreenState, ContextReport, ActionRecommendation
from ai_controller import DesktopAgentController


def test_context_chrome_profile_picker():
    analyzer = ContextAnalyzer()
    obs = {
        "active_window": "Who's using Chrome?",
        "elements": [
            {"id": 1, "role": "Text", "name": "Who's using Chrome?", "box": [400, 100, 600, 150]},
            {"id": 2, "role": "Button", "name": "Arpita Pawar (Default)", "box": [450, 200, 550, 300], "center": [500, 250]},
            {"id": 3, "role": "Button", "name": "Work Profile", "box": [600, 200, 700, 300], "center": [650, 250]},
        ],
    }

    report = analyzer.analyze(obs)
    assert report.state == ScreenState.CHROME_PROFILE_PICKER
    assert "multiple Chrome profiles" in report.situation
    assert "I see multiple Chrome profiles" in report.utterance
    assert report.recommendation.action_type == "click_element"
    assert report.recommendation.target_id == 2


def test_context_chrome_occupied_tab():
    analyzer = ContextAnalyzer()
    obs = {
        "active_window": "Review my PR diff - Claude - Google Chrome",
        "elements": [
            {"id": 1, "role": "TabItem", "name": "Review my PR diff - Claude", "box": [100, 10, 250, 40]},
            {"id": 2, "role": "Button", "name": "New Tab", "box": [260, 10, 290, 40]},
            {"id": 3, "role": "Edit", "name": "Address and search bar", "box": [100, 50, 800, 80]},
        ],
    }

    report = analyzer.analyze(obs, goal="instagram")
    assert report.state == ScreenState.CHROME_OCCUPIED_TAB
    assert "Something is already present" in report.utterance
    assert "create a new tab" in report.utterance
    assert report.recommendation.action_type == "hotkey"
    assert report.recommendation.hotkey == ["ctrl", "t"]


def test_context_chrome_new_tab():
    analyzer = ContextAnalyzer()
    obs = {
        "active_window": "New Tab - Google Chrome",
        "elements": [
            {"id": 1, "role": "TabItem", "name": "New Tab", "box": [100, 10, 250, 40]},
            {"id": 2, "role": "Edit", "name": "Address and search bar", "box": [100, 50, 800, 80]},
        ],
    }

    report = analyzer.analyze(obs)
    assert report.state == ScreenState.CHROME_NEW_TAB
    assert "clean tab" in report.utterance
    assert report.recommendation.action_type == "click_element"
    assert report.recommendation.target_id == 2


def test_context_instagram_login_form():
    analyzer = ContextAnalyzer()
    obs = {
        "active_window": "Instagram - Google Chrome",
        "elements": [
            {"id": 10, "role": "Edit", "name": "Mobile number, username or email", "box": [500, 300, 800, 340]},
            {"id": 11, "role": "Edit", "name": "Password", "box": [500, 360, 800, 400]},
            {"id": 12, "role": "Button", "name": "Log in", "box": [500, 420, 800, 460]},
        ],
    }

    report = analyzer.analyze(obs)
    assert report.state == ScreenState.INSTAGRAM_LOGIN_FORM
    assert "Instagram login form detected" in report.utterance
    assert report.recommendation.action_type == "click_element"
    assert report.recommendation.target_id == 10


def test_context_instagram_autofill():
    analyzer = ContextAnalyzer()
    obs = {
        "active_window": "Instagram - Google Chrome",
        "elements": [
            {"id": 10, "role": "Edit", "name": "Mobile number, username or email", "box": [500, 300, 800, 340]},
            {"id": 15, "role": "ListItem", "name": "pawararpita583@gmail.com", "box": [500, 350, 800, 390]},
            {"id": 12, "role": "Button", "name": "Log in", "box": [500, 420, 800, 460]},
        ],
    }

    report = analyzer.analyze(obs)
    assert report.state == ScreenState.INSTAGRAM_AUTOFILL_AVAILABLE
    assert "pawararpita583@gmail.com" in report.utterance
    assert report.recommendation.action_type == "click_element"
    assert report.recommendation.target_id == 15


def test_context_modal_dialog_dismiss():
    analyzer = ContextAnalyzer()
    obs = {
        "active_window": "Google Chrome",
        "elements": [
            {"id": 1, "role": "Dialog", "name": "Restore pages? Chrome didn't shut down correctly.", "box": [400, 100, 700, 300]},
            {"id": 2, "role": "Button", "name": "Restore", "box": [550, 250, 620, 280]},
            {"id": 3, "role": "Button", "name": "Close", "box": [630, 250, 690, 280]},
        ],
    }

    report = analyzer.analyze(obs)
    assert report.state == ScreenState.DIALOG_POPUP
    assert "dialog popup" in report.utterance
    assert report.recommendation.action_type == "click_element"
    assert report.recommendation.target_id == 3


def test_controller_analyze_context():
    controller = DesktopAgentController()
    obs = {
        "active_window": "New Tab - Google Chrome",
        "elements": [
            {"id": 1, "role": "TabItem", "name": "New Tab", "box": [100, 10, 250, 40]},
            {"id": 2, "role": "Edit", "name": "Address and search bar", "box": [100, 50, 800, 80]},
        ],
    }
    report = controller.analyze_context(observation=obs)
    assert isinstance(report, ContextReport)
    assert report.state == ScreenState.CHROME_NEW_TAB

    step_res = controller.step_with_context(goal=None, execute=False)
    assert step_res["success"] is True
    assert "utterance" in step_res
