"""Unit tests for agent_server API, authentication, validation, and concurrency."""

from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

import agent_server
from agent_server import app, get_current_token


@pytest.fixture
def client():
    """Create a TestClient with host set to testserver."""
    return TestClient(app, base_url="http://testserver")


@pytest.fixture
def auth_headers():
    token = get_current_token()
    return {"Authorization": f"Bearer {token}"}


# ── Health & Public Endpoints ────────────────────────────────────────────────
def test_health_public_access(client):
    """GET /health must be accessible without any credentials."""
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


# ── Host Header / DNS Rebinding Protection ───────────────────────────────────
def test_host_header_allowed(client):
    """Localhost and 127.0.0.1 must be allowed through Host header check."""
    resp = client.get("/health", headers={"Host": "127.0.0.1:8765"})
    assert resp.status_code == 200

    resp2 = client.get("/health", headers={"Host": "localhost:8765"})
    assert resp2.status_code == 200


def test_host_header_forbidden(client):
    """External or rebinding host headers must be blocked with 403."""
    resp = client.get("/health", headers={"Host": "attacker.com"})
    assert resp.status_code == 403
    assert "DNS rebinding" in resp.json()["detail"]


# ── Bearer Token Authentication ──────────────────────────────────────────────
def test_auth_missing_token(client):
    """Operational endpoints require authentication token."""
    resp = client.get("/eyes/info")
    assert resp.status_code == 401
    assert "WWW-Authenticate" in resp.headers


def test_auth_invalid_token(client):
    """Invalid token must be rejected with 401."""
    resp = client.get("/eyes/info", headers={"Authorization": "Bearer bad_token_12345"})
    assert resp.status_code == 401


def test_auth_valid_bearer_token(client, auth_headers):
    """Valid Bearer token grants access."""
    with patch("agent_server.eyes.get_screen_info", return_value={"width": 1920, "height": 1080}):
        resp = client.get("/eyes/info", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["width"] == 1920


def test_auth_valid_x_agent_token(client):
    """X-Agent-Token header is also accepted."""
    token = get_current_token()
    with patch("agent_server.eyes.get_screen_info", return_value={"width": 1920, "height": 1080}):
        resp = client.get("/eyes/info", headers={"X-Agent-Token": token})
        assert resp.status_code == 200


# ── Request Validation: ClickRequest ─────────────────────────────────────────
def test_click_validation_both_coords_or_none(client, auth_headers):
    """Click accepts either both x and y, or neither (current position)."""
    with patch("agent_server.hands_mouse.click", return_value={"success": True}):
        # Neither coordinate provided: OK
        resp = client.post("/hands/click", json={"button": "left"}, headers=auth_headers)
        assert resp.status_code == 200

        # Both coordinates provided: OK
        resp2 = client.post("/hands/click", json={"x": 500, "y": 300}, headers=auth_headers)
        assert resp2.status_code == 200

        # Only x provided: 422 Error
        resp3 = client.post("/hands/click", json={"x": 500}, headers=auth_headers)
        assert resp3.status_code == 422

        # Only y provided: 422 Error
        resp4 = client.post("/hands/click", json={"y": 300}, headers=auth_headers)
        assert resp4.status_code == 422


def test_click_validation_button_literal(client, auth_headers):
    """Click only accepts literal left, right, middle."""
    with patch("agent_server.hands_mouse.click", return_value={"success": True}):
        for valid_btn in ["left", "right", "middle"]:
            resp = client.post("/hands/click", json={"button": valid_btn}, headers=auth_headers)
            assert resp.status_code == 200

        # Invalid button value: 422 Error
        bad_resp = client.post("/hands/click", json={"button": "super_click"}, headers=auth_headers)
        assert bad_resp.status_code == 422


# ── Request Validation: TypeRequest & ScrollRequest ──────────────────────────
def test_type_profile_literal_validation(client, auth_headers):
    """Typing endpoint strictly validates typing profile Literal."""
    with patch("agent_server.TypingEngine.type_text", return_value={"success": True, "typed": "abc"}):
        for profile in ["natural", "fast", "careful", "coder"]:
            resp = client.post(
                "/hands/type",
                json={"text": "hello", "profile": profile},
                headers=auth_headers,
            )
            assert resp.status_code == 200

        bad_resp = client.post(
            "/hands/type",
            json={"text": "hello", "profile": "ultra_fast"},
            headers=auth_headers,
        )
        assert bad_resp.status_code == 422


def test_scroll_coordinate_validation(client, auth_headers):
    """Scroll accepts either both x and y, or neither."""
    with patch("agent_server.hands_mouse.scroll", return_value={"success": True}):
        resp1 = client.post("/hands/scroll", json={"clicks": 5}, headers=auth_headers)
        assert resp1.status_code == 200

        resp2 = client.post("/hands/scroll", json={"clicks": 5, "x": 100, "y": 200}, headers=auth_headers)
        assert resp2.status_code == 200

        resp3 = client.post("/hands/scroll", json={"clicks": 5, "x": 100}, headers=auth_headers)
        assert resp3.status_code == 422


# ── Paste with Clipboard Restoration ─────────────────────────────────────────
def test_paste_endpoint(client, auth_headers):
    """Paste supports restore_clipboard option."""
    with patch("agent_server.hands_keyboard.fast_paste") as mock_paste:
        resp = client.post(
            "/hands/paste",
            json={"text": "secure_text", "restore_clipboard": True},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["clipboard_restored"] is True
        mock_paste.assert_called_once_with("secure_text", restore_clipboard=True)


# ── Task Lifecycle & Ephemeral Cleanup ───────────────────────────────────────
def test_task_lifecycle(client, auth_headers):
    """Starting and ending a task session works safely."""
    mock_session = MagicMock()
    mock_session.task_name = "test_run"

    with patch("agent_server.eyes.start_task", return_value=mock_session), \
         patch("agent_server.eyes.end_task", return_value=3):

        start_resp = client.post("/eyes/task/start", json={"task_name": "test_run"}, headers=auth_headers)
        assert start_resp.status_code == 200
        assert start_resp.json()["task_name"] == "test_run"
        assert "session_id" in start_resp.json()

        end_resp = client.post("/eyes/task/end", headers=auth_headers)
        assert end_resp.status_code == 200
        assert end_resp.json()["deleted_screenshots"] == 3
