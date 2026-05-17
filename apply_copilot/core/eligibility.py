"""Pre-flight: scan a JD for hard disqualifiers (citizen-only, clearance-only,
BS-only). Returns the matched phrase or empty string.

Saves ~$0.25 of LLM cost per skipped job.
"""
from __future__ import annotations
import re


# Order: most-specific patterns first
ELIGIBILITY_DISQUALIFIERS = [
    r"\bU\.?S\.?\s+citizen", r"\bU\.?S\.?\s+citizenship",
    r"\bcitizens\s+only", r"citizenship\s+is\s+required",
    r"permanent\s+resident(?:s|cy)?\s+(?:only|required)",
    r"green\s+card\s+(?:only|required|holder)",
    r"must\s+(?:be|hold).{0,30}(?:citizen|permanent\s+resident|green\s+card)",
    # Sponsorship intentionally left OUT — many users still apply and negotiate
    r"bachelor.{0,5}(?:degree|s)\s+only",
    r"undergraduate\s+only",
    r"(?:rising\s+)?senior\s+only",
    r"must\s+be\s+enrolled\s+in.{0,40}(?:bachelor|undergrad)",
    r"\bSecret\s+(?:security\s+)?clearance",
    r"Top\s+Secret\s+clearance",
    r"active\s+clearance",
]
_REGEX = re.compile("|".join(ELIGIBILITY_DISQUALIFIERS), re.I)


def disqualifier(jd: str) -> str:
    """Return the matched disqualifier phrase, or empty string if none."""
    if not jd:
        return ""
    m = _REGEX.search(jd)
    return m.group(0).strip() if m else ""
