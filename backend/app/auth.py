"""Authentication contract for the local extension-to-API channel."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import secrets

from .config import settings


APP_ID = "jp.clarith.local-api"
PROTOCOL_VERSION = 1
TOKEN_HEADER = "X-Clarith-Token"
STARTUP_NONCE = secrets.token_urlsafe(24)


@dataclass(frozen=True)
class AuthConfig:
    token: str


def load_auth_config(path: Path | None = None) -> AuthConfig | None:
    config_path = path or settings.auth_config_path
    if not config_path.is_file():
        return None
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
        token = payload["apiToken"]
    except (OSError, json.JSONDecodeError, KeyError, TypeError):
        return None
    if not isinstance(token, str) or len(token) < 32:
        return None
    return AuthConfig(token=token)


def configured_token() -> str | None:
    if settings.api_token:
        return settings.api_token
    config = load_auth_config()
    return config.token if config else None


def token_matches(provided: str | None) -> bool:
    expected = configured_token()
    return bool(expected and provided and secrets.compare_digest(expected, provided))

