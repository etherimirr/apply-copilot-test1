"""Unit tests for the label-driven field classifier."""
from __future__ import annotations
import pytest

from apply_copilot.platforms.ats.field_classify import (
    classify_field, value_for, is_demographic,
)


@pytest.mark.parametrize("label,expected_type,expected_key", [
    ("First Name *", "first_name", "first_name"),
    ("Last name", "last_name", "last_name"),
    ("Email Address", "email", "email"),
    ("Phone", "phone", "phone"),
    ("LinkedIn URL", "linkedin", "linkedin"),
    ("GitHub", "github", "github"),
    ("University", "school", "school"),
    ("Field of Study", "field_of_study", "school_major"),
    ("GPA", "gpa", "school_gpa"),
    ("Years of Experience", "years_experience", "years_of_experience"),
    ("Zip code", "postal_code", "postal_code"),
    ("City", "city", "city"),
])
def test_classify_common_fields(label, expected_type, expected_key):
    result = classify_field(label)
    assert result is not None, f"failed to classify {label!r}"
    assert result == (expected_type, expected_key)


def test_classify_work_auth_before_address():
    """work_auth rules MUST match before address2 (which catches 'unit' in 'United States')."""
    r = classify_field("Are you legally authorized to work in the United States?")
    assert r == ("work_auth_us", "work_auth_us")


def test_classify_sponsorship():
    r = classify_field("Will you now or in the future require sponsorship for an H-1B visa?")
    assert r == ("needs_sponsorship", "need_sponsorship")


def test_classify_file_resume():
    r = classify_field("Resume / CV *", input_type="file")
    assert r[0] == "resume"


def test_classify_file_cover_letter():
    r = classify_field("Cover Letter (optional)", input_type="file")
    assert r[0] == "cover_letter"


def test_classify_file_with_random_label_defaults_to_resume():
    """File slots with any label that doesn't match cover_letter/transcript/
    portfolio fall through to the resume default — filler then uploads the
    resume PDF."""
    r = classify_field("Upload your document", input_type="file")
    assert r == ("resume", None)


def test_classify_empty_file_label_returns_none():
    """A truly empty label set returns None — the filler itself defaults to
    resume when classify returns None, so this matches by design."""
    assert classify_field("", input_type="file") is None


def test_classify_unknown_returns_none():
    r = classify_field("What is your favorite color?")
    assert r is None


def test_classify_empty():
    assert classify_field("") is None
    assert classify_field("   ") is None


def test_value_for_uses_profile():
    profile = {"first_name": "Alex", "email": "alex@example.com"}
    assert value_for("first_name", profile, "first_name") == "Alex"
    assert value_for("email", profile, "email") == "alex@example.com"


def test_value_for_missing_key_returns_empty():
    assert value_for("first_name", {}, "first_name") == ""


def test_value_for_summary_fallback():
    profile = {"summary": "An ML engineer with 3 years experience."}
    assert value_for("summary", profile) == profile["summary"]


def test_is_demographic():
    assert is_demographic("race")
    assert is_demographic("gender") is False  # gender is generally fillable
    assert is_demographic("disability")
    assert is_demographic("first_name") is False
