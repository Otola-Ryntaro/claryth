"""Shared database bootstrap for backend tests."""

import os

import pytest

os.environ.setdefault("CLARITH_API_TOKEN", "test-token-0123456789-abcdefghijklmnopqrstuvwxyz")

from backend.app.database import initialize_database
from backend.app import top20


@pytest.fixture(scope="session", autouse=True)
def seeded_database() -> None:
    initialize_database()


@pytest.fixture
def clinically_reviewed_top20(monkeypatch: pytest.MonkeyPatch) -> None:
    from backend.app import main
    from backend.app.integrity import IntegrityResult

    monkeypatch.setattr(top20, "clinically_ready", lambda: True)
    result = IntegrityResult(True, "ok", "test", "2099-01-01T00:00:00+00:00")
    monkeypatch.setattr(main, "verify_release_manifest", lambda: result)
    monkeypatch.setattr(main, "release_integrity", result)
