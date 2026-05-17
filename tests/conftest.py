"""Shared fixtures: isolated APPLY_COPILOT_HOME per test, fresh SQLite."""
from __future__ import annotations
import importlib
import os
import sys
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolated_data_root(tmp_path, monkeypatch):
    """Every test gets its own ~/.apply_copilot equivalent.
    Re-imports config + storage modules so they pick up the new env var.
    """
    monkeypatch.setenv("APPLY_COPILOT_HOME", str(tmp_path / ".apply_copilot"))
    # Reload modules that cached the data root at import time
    for mod in [
        "apply_copilot.config", "apply_copilot.storage.db",
        "apply_copilot.storage.models", "apply_copilot.storage",
        "apply_copilot.core.qa_memory",
    ]:
        if mod in sys.modules:
            importlib.reload(sys.modules[mod])
    yield tmp_path
