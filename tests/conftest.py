"""Shared database bootstrap for backend tests."""

import pytest

from backend.app.database import initialize_database


@pytest.fixture(scope="session", autouse=True)
def seeded_database() -> None:
    initialize_database()

