"""Tests for the cover-letter critic — pure string checks, no LLM."""
from __future__ import annotations
from apply_copilot.core.cl_writer import critic_check


def test_empty_text():
    assert critic_check("") == ["empty"]


def test_clean_letter_passes():
    text = (
        "Dear hiring team,\n\nMy work on Python and PyTorch ranking models at "
        "Acme matches your need for ML infrastructure. I built a retrieval "
        "system handling 40K users.\n\nWould welcome an interview to discuss.\n"
    )
    issues = critic_check(text)
    assert issues == []


def test_catches_em_dash():
    text = "I built a system — it ranks well. Please consider me."
    assert "contains em/en dash" in critic_check(text)


def test_catches_en_dash():
    text = "I built a system – it ranks well. Please consider me."
    assert "contains em/en dash" in critic_check(text)


def test_catches_cliche_leverage():
    text = "I leverage Python to ship features. Please consider me."
    issues = critic_check(text)
    assert any("leverage" in i for i in issues)


def test_catches_cliche_transformative():
    text = "I love transformative AI. Please consider me."
    issues = critic_check(text)
    assert any("transformative" in i for i in issues)


def test_catches_third_person_the_company():
    text = "I respect the company's mission. I bring strong ML skills."
    issues = critic_check(text)
    assert any("third-person" in i for i in issues)


def test_catches_pr_reference():
    text = "I contributed to PR #4521 in a recent project."
    issues = critic_check(text)
    assert any("PR" in i for i in issues)


def test_catches_coursework_code():
    text = "In E6892 I built a recommendation engine."
    issues = critic_check(text)
    assert any("coursework" in i for i in issues)


def test_too_long_triggers_warning():
    text = "word " * 600
    issues = critic_check(text)
    assert any("too long" in i for i in issues)
