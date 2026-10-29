"""Tests for environment-backed application settings."""
import pytest

from config.settings import AgentSettings


def test_defaults_preserve_localhost_configuration(monkeypatch):
    for name in (
        "AGENT_HOST", "AGENT_PORT", "AGENT_BASE_URL",
        "ALLOWED_HOSTS", "CORS_ORIGINS",
    ):
        monkeypatch.delenv(name, raising=False)

    settings = AgentSettings.from_env()

    assert settings.server_host == "127.0.0.1"
    assert settings.server_port == 8765
    assert "localhost" in settings.allowed_hosts
    assert "127.0.0.1" in settings.allowed_hosts
    assert settings.api_base_url == "http://127.0.0.1:8765"
    assert settings.cors_origins == (
        "http://127.0.0.1:8765",
        "http://localhost:8765",
    )


def test_environment_overrides_are_applied(monkeypatch):
    monkeypatch.setenv("AGENT_HOST", "127.0.0.1")
    monkeypatch.setenv("AGENT_PORT", "9001")
    monkeypatch.setenv("AGENT_BASE_URL", "http://localhost:9001/")
    monkeypatch.setenv("ALLOWED_HOSTS", "devbox.local,localhost")
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:3000,https://ui.example.test")

    settings = AgentSettings.from_env()

    assert settings.server_port == 9001
    assert settings.api_base_url == "http://localhost:9001"
    assert "devbox.local" in settings.allowed_hosts
    assert settings.cors_origins == (
        "http://localhost:3000",
        "https://ui.example.test",
    )


@pytest.mark.parametrize("port", ["0", "65536", "not-a-port", ""])
def test_invalid_port_is_rejected(monkeypatch, port):
    monkeypatch.setenv("AGENT_PORT", port)

    with pytest.raises(ValueError, match="AGENT_PORT"):
        AgentSettings.from_env()


def test_invalid_base_url_is_rejected(monkeypatch):
    monkeypatch.setenv("AGENT_BASE_URL", "localhost:8765")

    with pytest.raises(ValueError, match="AGENT_BASE_URL"):
        AgentSettings.from_env()
