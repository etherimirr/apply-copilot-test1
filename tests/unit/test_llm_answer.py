"""Unit tests for the open-question answerer.

Only tests the offline parts (yes_no_for + qa_memory cache hit). The
live LLM path is not unit-tested — it's covered by integration smoke.
"""
from __future__ import annotations
from apply_copilot.core.llm_answer import yes_no_for, answer_question
from apply_copilot.core import qa_memory


def test_yes_no_work_auth_default():
    assert yes_no_for("Are you legally authorized to work in the U.S.?", {}) == "Yes"


def test_yes_no_work_auth_profile_override():
    profile = {"work_auth_us": "No"}
    assert yes_no_for("Are you authorized to work in the US?", profile) == "No"


def test_yes_no_sponsorship_default():
    """When the user doesn't override, defaults to "No" for sponsorship —
    candidate-friendly to most employers."""
    assert yes_no_for("Will you require sponsorship for employment?", {}) == "No"


def test_yes_no_sponsorship_h1b_keyword():
    assert yes_no_for("Do you need an H-1B?", {}) == "No"


def test_yes_no_relocate_default():
    assert yes_no_for("Are you willing to relocate?", {}) == "Yes"


def test_yes_no_18_years():
    assert yes_no_for("Are you 18 years or older?", {}) == "Yes"


def test_yes_no_felony():
    assert yes_no_for("Have you been convicted of a felony?", {}) == "No"


def test_yes_no_noncompete():
    assert yes_no_for("Are you currently bound by a non-compete agreement?", {}) == "No"


def test_yes_no_unmatched_returns_none():
    assert yes_no_for("What is your favorite framework?", {}) is None


def test_answer_question_short_returns_empty():
    assert answer_question("hi") == ""
    assert answer_question("") == ""


def test_answer_question_uses_qa_memory_cache():
    """If qa_memory already has the answer, we should return it without LLM."""
    qa_memory.save("Why this company?", "I love their mission and have worked on related problems.",
                    company="Acme")
    out = answer_question("Why this company?")
    assert "love their mission" in out
