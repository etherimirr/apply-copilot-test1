"""Unit: eligibility regex — must catch citizenship/clearance/BS-only, must NOT
catch arbitrary mentions of 'unit', 'address', etc."""
from __future__ import annotations
import pytest

from apply_copilot.core.eligibility import disqualifier


@pytest.mark.parametrize("jd,expected_substr", [
    ("Must be a U.S. citizen.", "citizen"),
    ("Applicants must be US citizens only.", "citizen"),
    ("Citizenship is required for this role.", "Citizenship"),
    ("Must hold permanent resident status.", "permanent resident"),
    ("Must be a U.S. citizen, lawful permanent resident, or...", "citizen"),
    ("Bachelor's degree only — no Master's applications accepted.", "Bachelor"),
    ("Undergraduate only.", "Undergraduate"),
    ("Active Secret security clearance required.", "Secret"),
    ("Top Secret clearance required.", "Top Secret"),
    # The "green card" rule is intentionally narrow: requires a qualifier
    # like "only" / "required" / "holder". Naked "green card or X" doesn't fire.
    ("Green card required.", "green card"),
    ("Must hold green card.", "green card"),
    ("Requires US citizenship.", "citizen"),
])
def test_catches_disqualifiers(jd, expected_substr):
    out = disqualifier(jd)
    assert expected_substr.lower() in out.lower(), f"missed {expected_substr!r} in {jd!r}"


@pytest.mark.parametrize("jd", [
    "",
    "We're a fast-growing startup based in the United States.",
    "Work directly with the unit-test framework.",
    "Address validation is part of the role.",
    "Open to international candidates; visa sponsorship available.",
    "Are you legally authorized to work in the United States?",
    # 👆 this last one is a *question*, not a disqualifier — should pass through
])
def test_no_false_positives(jd):
    """Phrases that LOOK like disqualifiers but aren't (United, Address, etc).
    The autopilot checks the JD body separately; here we just ensure the regex
    doesn't fire on normal English mentioning 'unit', 'address', etc."""
    out = disqualifier(jd)
    # Some of these (legitimate work-auth question) DO contain US-citizen-like
    # words, but the regex was tuned to skip "are you authorized" style asks.
    # Empty result expected.
    assert out == "", f"false positive on {jd!r}: matched {out!r}"


def test_no_sponsorship_is_NOT_disqualifier():
    """Christina explicitly opted out of 'no sponsorship' disqualifier so that
    she can still apply and ask in interview. See feedback memory."""
    out = disqualifier("Unable to sponsor work visas at this time.")
    assert out == ""
