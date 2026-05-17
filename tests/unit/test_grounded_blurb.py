"""Tests for project-picker + scrub utility (offline parts of grounded_blurb)."""
from __future__ import annotations
from apply_copilot.core.grounded_blurb import (
    pick_project_for_question, _scrub,
)


def test_pick_project_empty_kb():
    assert pick_project_for_question(question="x", project_kb={}) is None


def test_pick_project_returns_only_entry():
    kb = {"jnj": "Built a healthcare data pipeline using Python and PostgreSQL."}
    assert pick_project_for_question(question="anything", project_kb=kb) == "jnj"


def test_pick_project_by_keyword_overlap():
    kb = {
        "jnj": "Healthcare data pipeline using Python.",
        "agent_bot": "Multi-agent assistant powered by Claude Code SDK.",
    }
    # Question mentions "agent" → should pick agent_bot
    pid = pick_project_for_question(
        question="Tell us about an agent project you've built.", project_kb=kb)
    assert pid == "agent_bot"


def test_pick_project_uses_jd_context():
    kb = {
        "fintech_app": "Trading dashboard using FastAPI and PostgreSQL.",
        "ml_pipeline": "Image generation pipeline with LoRA fine-tuning.",
    }
    pid = pick_project_for_question(
        question="Describe a relevant project.",
        project_kb=kb,
        jd="We are looking for fine-tuning experience and LoRA adapter work.",
    )
    assert pid == "ml_pipeline"


def test_scrub_removes_em_dash():
    assert "—" not in _scrub("I built a system — it ranks well.")


def test_scrub_removes_en_dash():
    assert "–" not in _scrub("I built a system – it ranks well.")


def test_scrub_strips_code_fence():
    inp = "```\nThis is the blurb.\n```"
    assert _scrub(inp).strip() == "This is the blurb."


def test_scrub_strips_language_code_fence():
    inp = "```text\nBlurb text here.\n```"
    out = _scrub(inp)
    assert "```" not in out
    assert "Blurb text here." in out
