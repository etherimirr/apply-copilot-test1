"""Unit: config module respects $APPLY_COPILOT_HOME, ensures dirs, paths use pathlib."""
from __future__ import annotations
import os
from pathlib import Path

from apply_copilot import config


def test_data_root_uses_env_var(isolated_data_root):
    """APPLY_COPILOT_HOME env var overrides default ~/.apply_copilot."""
    expected = isolated_data_root / ".apply_copilot"
    assert Path(os.environ["APPLY_COPILOT_HOME"]) == expected
    # config.py was reloaded by fixture → should point at the override
    assert config.DATA_ROOT == expected


def test_paths_are_under_data_root():
    """Every derived path lives under DATA_ROOT (no rogue absolute paths)."""
    root = config.DATA_ROOT
    for p in (config.PROFILE_JSON, config.QA_MEMORY_JSON, config.SUBMISSIONS_DB,
              config.RESUMES_DIR, config.GENERATED_DIR, config.BROWSER_PROFILE,
              config.LOGS_DIR, config.SCREENSHOTS_DIR):
        assert str(p).startswith(str(root)), f"{p} escapes DATA_ROOT {root}"


def test_ensure_dirs_creates_all():
    """ensure_dirs() creates the data tree."""
    config.ensure_dirs()
    for d in (config.DATA_ROOT, config.RESUMES_DIR, config.GENERATED_DIR,
              config.BROWSER_PROFILE, config.LOGS_DIR, config.SCREENSHOTS_DIR):
        assert d.is_dir(), f"{d} not created"


def test_resume_directions_includes_default():
    """The 'default' direction must exist as a catch-all."""
    assert "default" in config.RESUME_DIRECTIONS


def test_pdf_page_count_handles_missing(tmp_path):
    """Missing PDF returns 0 without raising."""
    fake = tmp_path / "nope.pdf"
    assert config.pdf_page_count(fake) == 0


def test_pdf_to_text_handles_missing(tmp_path):
    """Missing PDF returns empty string without raising."""
    fake = tmp_path / "nope.pdf"
    assert config.pdf_to_text(fake) == ""
