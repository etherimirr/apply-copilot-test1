"""Unit: QA memory — save, exact lookup, fuzzy lookup, near-dup replace."""
from __future__ import annotations
import pytest

from apply_copilot.core import qa_memory


def test_lookup_empty_when_no_entries():
    assert qa_memory.lookup("Why this company?") is None


def test_save_then_lookup_exact():
    qa_memory.save("Why this company?", "I want to learn at X.", company="X")
    hit = qa_memory.lookup("Why this company?")
    assert hit is not None
    assert hit["a"] == "I want to learn at X."


def test_lookup_fuzzy_variant():
    """Token-Jaccard with stopwords removed matches 'why' + 'company'."""
    qa_memory.save("Why this company?", "I want to learn at X.")
    hit = qa_memory.lookup("Why are you interested in this company?")
    assert hit is not None
    assert "I want to learn" in hit["a"]


def test_lookup_below_threshold_returns_none():
    qa_memory.save("Why this company?", "...")
    # Completely unrelated content
    assert qa_memory.lookup("Describe your experience with Kafka") is None


def test_save_near_dup_replaces_answer():
    """A second save with the same question (≥0.9 sim) replaces the answer
    in place rather than appending a new entry."""
    qa_memory.save("Why this company?", "first answer")
    qa_memory.save("Why this company?", "second answer")
    entries = qa_memory.all_entries()
    assert len(entries) == 1
    assert entries[0]["a"] == "second answer"


def test_save_distinct_questions_appended():
    qa_memory.save("Q one short string here", "A1")
    qa_memory.save("Q two different unrelated content", "A2")
    assert len(qa_memory.all_entries()) == 2


def test_lookup_bumps_uses_counter():
    qa_memory.save("Why this company?", "A")
    qa_memory.lookup("Why this company?")
    qa_memory.lookup("Why this company?")
    assert qa_memory.all_entries()[0]["uses"] >= 3


@pytest.mark.parametrize("q", ["", "   ", "tiny"])
def test_lookup_rejects_too_short(q):
    qa_memory.save("Why this company?", "A")
    assert qa_memory.lookup(q) is None
