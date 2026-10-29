"""Centralized environment-backed runtime settings."""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env", override=False)


def _csv_setting(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return tuple(value.strip() for value in raw.split(",") if value.strip())


@dataclass(frozen=True)
class AgentSettings:
    """Validated runtime configuration for the desktop agent and REST API."""

    server_host: str
    server_port: int
    allowed_hosts: tuple[str, ...]
    cors_origins: tuple[str, ...]
    api_base_url: str

    @classmethod
    def from_env(cls) -> "AgentSettings":
        """Build settings from the current process environment."""
        host = os.environ.get("AGENT_HOST", "127.0.0.1").strip()
        if not host:
            raise ValueError("AGENT_HOST must not be empty.")

        raw_port = os.environ.get("AGENT_PORT", "8765").strip()
        try:
            port = int(raw_port)
        except ValueError as exc:
            raise ValueError("AGENT_PORT must be an integer between 1 and 65535.") from exc
        if not 1 <= port <= 65535:
            raise ValueError("AGENT_PORT must be an integer between 1 and 65535.")

        default_hosts = ("127.0.0.1", "localhost", "testserver")
        configured_hosts = _csv_setting("ALLOWED_HOSTS", ())
        allowed_hosts = tuple(dict.fromkeys(
            value.lower() for value in (*default_hosts, *configured_hosts)
        ))

        default_origins = (
            f"http://127.0.0.1:{port}",
            f"http://localhost:{port}",
        )
        cors_origins = _csv_setting("CORS_ORIGINS", default_origins)
        api_base_url = os.environ.get(
            "AGENT_BASE_URL", f"http://127.0.0.1:{port}"
        ).strip().rstrip("/")
        if not api_base_url.startswith(("http://", "https://")):
            raise ValueError("AGENT_BASE_URL must begin with http:// or https://.")

        return cls(
            server_host=host,
            server_port=port,
            allowed_hosts=allowed_hosts,
            cors_origins=cors_origins,
            api_base_url=api_base_url,
        )


settings = AgentSettings.from_env()
