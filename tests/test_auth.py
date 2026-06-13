"""Local API authentication and credential-file tests."""

import json
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from backend.app.auth import APP_ID, PROTOCOL_VERSION, load_auth_config
from backend.app.main import app


VALID_TOKEN = "test-token-0123456789-abcdefghijklmnopqrstuvwxyz"


def test_health_reports_identity_and_authentication_state() -> None:
    with TestClient(app) as client:
        public = client.get("/health")
        authenticated = client.get("/health", headers={"X-Clarith-Token": VALID_TOKEN})
    assert public.status_code == 200
    assert public.json()["app_id"] == APP_ID
    assert public.json()["protocol_version"] == PROTOCOL_VERSION
    assert public.json()["authenticated"] is False
    assert public.json()["startup_nonce"]
    assert authenticated.json()["authenticated"] is True


def test_protected_api_requires_matching_token() -> None:
    with TestClient(app) as client:
        missing = client.get("/v1/dataset")
        invalid = client.get("/v1/dataset", headers={"X-Clarith-Token": "x" * 48})
        valid = client.get("/v1/dataset", headers={"X-Clarith-Token": VALID_TOKEN})
    assert missing.status_code == 401
    assert invalid.status_code == 403
    assert valid.status_code == 200


def test_protected_api_fails_closed_when_auth_is_unconfigured() -> None:
    from unittest.mock import patch

    with patch("backend.app.main.configured_token", return_value=None):
        with TestClient(app) as client:
            response = client.get("/v1/dataset", headers={"X-Clarith-Token": VALID_TOKEN})
    assert response.status_code == 503


def temporary_auth_file() -> Path:
    path = Path("tests") / f".auth-{uuid4().hex}.json"
    return path


def test_auth_config_loads_new_token_after_rotation() -> None:
    auth_file = temporary_auth_file()
    first = "a" * 43
    second = "b" * 43
    try:
        auth_file.write_text(json.dumps({"apiToken": first}), encoding="utf-8")
        assert load_auth_config(auth_file).token == first
        auth_file.write_text(json.dumps({"apiToken": second}), encoding="utf-8")
        assert load_auth_config(auth_file).token == second
    finally:
        auth_file.unlink(missing_ok=True)


def test_auth_config_rejects_missing_or_short_tokens() -> None:
    missing = temporary_auth_file()
    invalid = temporary_auth_file()
    try:
        invalid.write_text(json.dumps({"apiToken": "short"}), encoding="utf-8")
        assert load_auth_config(missing) is None
        assert load_auth_config(invalid) is None
    finally:
        invalid.unlink(missing_ok=True)
