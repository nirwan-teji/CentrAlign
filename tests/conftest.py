# tests/conftest.py — Shared pytest fixtures
from __future__ import annotations

import asyncio
import pytest


@pytest.fixture(scope="session")
def event_loop():
    """Provide a session-scoped event loop for all async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()
