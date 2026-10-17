"""Unit tests for DesktopAgentClient."""

import os
from unittest.mock import MagicMock, patch
import pytest

from api_client import DesktopAgentClient


def test_client_init_with_token():
    client = DesktopAgentClient(base_url="http://127.0.0.1:8765", auth_token="my_test_token")
    assert client.session.headers.get("Authorization") == "Bearer my_test_token"


def test_client_init_from_env():
    with patch.dict(os.environ, {"AGENT_AUTH_TOKEN": "env_token_abc"}):
        client = DesktopAgentClient(base_url="http://127.0.0.1:8765")
        assert client.session.headers.get("Authorization") == "Bearer env_token_abc"


def test_client_click_coordinates():
    client = DesktopAgentClient(base_url="http://127.0.0.1:8765", auth_token="tok")
    with patch.object(client.session, "post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"success": True}
        mock_post.return_value = mock_resp

        client.click(100, 200, button="right", clicks=2)

        mock_post.assert_called_once()
        call_url = mock_post.call_args[0][0]
        call_json = mock_post.call_args[1]["json"]
        assert call_url.endswith("/hands/click")
        assert call_json == {"button": "right", "clicks": 2, "x": 100, "y": 200}


def test_client_task_context_manager():
    client = DesktopAgentClient(base_url="http://127.0.0.1:8765", auth_token="tok")
    with patch.object(client, "start_task") as mock_start, \
         patch.object(client, "end_task") as mock_end:

        with client.task("automated_job"):
            pass

        mock_start.assert_called_once_with("automated_job")
        mock_end.assert_called_once()


def test_client_observe():
    client = DesktopAgentClient(base_url="http://127.0.0.1:8765", auth_token="tok")
    with patch.object(client.session, "post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"success": True, "observation_id": "obs_1"}
        mock_post.return_value = mock_resp

        res = client.observe(save_annotated=True, max_elements=50)
        assert res["observation_id"] == "obs_1"
        call_url = mock_post.call_args[0][0]
        assert call_url.endswith("/eyes/observe")


def test_client_click_element():
    client = DesktopAgentClient(base_url="http://127.0.0.1:8765", auth_token="tok")
    with patch.object(client.session, "post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"success": True}
        mock_post.return_value = mock_resp

        client.click_element(3, button="middle")
        call_url = mock_post.call_args[0][0]
        call_json = mock_post.call_args[1]["json"]
        assert call_url.endswith("/hands/click_element")
        assert call_json == {"element_id": 3, "button": "middle", "clicks": 1}

