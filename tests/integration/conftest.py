"""Integration conftest: build a fresh FastAPI TestClient per test."""
from __future__ import annotations
import importlib
import sys
import pytest


@pytest.fixture
def client():
    """Re-import server modules after isolated_data_root has set env vars,
    then return a TestClient. Avoid stale module caches between tests."""
    # Drop server modules so they pick up the fresh config/storage
    for mod in list(sys.modules):
        if mod.startswith("apply_copilot.server"):
            del sys.modules[mod]
    from apply_copilot.storage import init_db
    init_db()
    from apply_copilot.server.main import app
    from fastapi.testclient import TestClient
    return TestClient(app)
