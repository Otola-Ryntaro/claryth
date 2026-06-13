"""API input, CORS, request-size, and resource-limit tests."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from backend.app.config import settings
from backend.app.main import app, request_guard
from backend.app.security import RequestGuard, RequestSizeLimitMiddleware


AUTH_HEADERS = {"X-Clarith-Token": "test-token-0123456789-abcdefghijklmnopqrstuvwxyz"}
EXTENSION_ORIGIN = settings.allowed_origins[0]


def client() -> TestClient:
    return TestClient(app, headers=AUTH_HEADERS)


def test_resolve_accepts_twenty_bounded_inputs() -> None:
    with client() as api:
        response = api.post("/v1/resolve", json={"inputs": [f"薬剤{i}" for i in range(20)]})
    assert response.status_code == 200
    assert len(response.json()["items"]) == 20


def test_resolve_rejects_more_than_twenty_names_in_text() -> None:
    with client() as api:
        response = api.post("/v1/resolve", json={"text": "\n".join(f"薬剤{i}" for i in range(21))})
    assert response.status_code == 422


def test_request_models_reject_unknown_fields_and_long_items() -> None:
    with client() as api:
        extra = api.post("/v1/resolve", json={"text": "ワーファリン", "unexpected": True})
        long_input = api.post("/v1/resolve", json={"inputs": ["薬" * 201]})
        long_id = api.post(
            "/v1/check",
            json={"items": [{"input_name": "薬剤", "drug_id": "x" * 129}]},
        )
    assert extra.status_code == 422
    assert long_input.status_code == 422
    assert long_id.status_code == 422


def test_oversized_json_body_is_rejected_before_validation() -> None:
    with client() as api:
        response = api.post("/v1/resolve", json={"text": "薬" * 20000})
    assert response.status_code == 413


def test_cors_preflight_allows_only_the_fixed_extension_origin() -> None:
    headers = {
        "Origin": EXTENSION_ORIGIN,
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type,x-clarith-token",
    }
    with client() as api:
        allowed = api.options("/v1/resolve", headers=headers)
        denied = api.options(
            "/v1/resolve",
            headers={**headers, "Origin": "chrome-extension://aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"},
        )
    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == EXTENSION_ORIGIN
    assert denied.status_code == 403
    assert "access-control-allow-origin" not in denied.headers


def test_product_mode_hides_api_documentation() -> None:
    assert settings.product_mode is True
    with client() as api:
        assert api.get("/docs").status_code == 404
        assert api.get("/redoc").status_code == 404
        assert api.get("/openapi.json").status_code == 404


def test_repeated_expensive_calls_are_rate_limited() -> None:
    request_guard.reset()
    try:
        with patch("backend.app.main.warmup_ollama", new=AsyncMock(return_value=True)):
            with client() as api:
                responses = [api.post("/v1/ollama/warmup") for _ in range(6)]
        assert [response.status_code for response in responses[:5]] == [200] * 5
        assert responses[5].status_code == 429
        assert int(responses[5].headers["retry-after"]) >= 1
    finally:
        request_guard.reset()


def test_concurrent_expensive_limit_rejects_without_waiting() -> None:
    guard = RequestGuard(
        max_concurrent=2,
        max_expensive=1,
        rate_limits={"/v1/resolve": 10},
    )
    first, _ = guard.try_enter("/v1/resolve")
    second, retry_after = guard.try_enter("/v1/resolve")
    assert first is not None
    assert second is None
    assert retry_after == 1
    guard.release(first)


def test_chunked_body_limit_does_not_depend_on_content_length() -> None:
    received = [
        {"type": "http.request", "body": b"1234", "more_body": True},
        {"type": "http.request", "body": b"5678", "more_body": False},
    ]
    sent: list[dict] = []

    async def consuming_app(scope, receive, send) -> None:
        while True:
            message = await receive()
            if not message.get("more_body"):
                break

    async def receive() -> dict:
        return received.pop(0)

    async def send(message: dict) -> None:
        sent.append(message)

    middleware = RequestSizeLimitMiddleware(consuming_app, max_bytes=7)
    asyncio.run(middleware({"type": "http", "headers": []}, receive, send))
    assert sent[0]["status"] == 413


def test_manifest_key_matches_the_allowed_extension_origin() -> None:
    manifest = json.loads(Path("extension/src/manifest.json").read_text(encoding="utf-8"))
    public_key = base64.b64decode(manifest["key"])
    digest = hashlib.sha256(public_key).digest()[:16]
    extension_id = "".join(chr(97 + (byte >> 4)) + chr(97 + (byte & 15)) for byte in digest)
    assert settings.allowed_origins == (f"chrome-extension://{extension_id}",)
