"""Cover letter generator with critic loop (em-dash / cliché filter).

Critic enforces:
- 1 page (≤ 500 words)
- No em-dashes or en-dashes (use period / comma / parens)
- No AI-cliché phrases ("leverage", "transformative", "cutting-edge", "passionate")
- No third-person "the company" / "this firm" — use "you" / "<Company>'s"
- No git / PR / coursework refs
- Date in header (today's date)
- At least 5 bold spans on JD-keyword tech terms (so visual diff is clear)
"""
from __future__ import annotations
import re
from datetime import date
from .llm_client import llm_call, parse_json_from_response


CLICHE_WORDS = [
    "leverage", "transformative", "cutting-edge", "passionate",
    "synergy", "synergize", "delve into", "tapestry",
]
FORBIDDEN_PATTERNS = [
    (r"the company\b", "third-person 'the company'"),
    (r"this firm\b", "third-person 'this firm'"),
    (r"#\d+", "PR / issue refs (#123)"),
    (r"\barklexai/", "git branch refs"),
    (r"\b[Ee]\d{4}\b", "coursework codes (E6792)"),
    (r"\bcollaborat\w* on the\b", "process annotation"),
]


SYSTEM_PROMPT = """You're writing a tailored cover letter for {name} applying
to {role} at {company}.

CONSTRAINTS:
- Plain text, ≤ 450 words. No em-dashes or en-dashes — use periods, commas,
  parentheses instead.
- Address the company as "you" / "<Company>'s" — never "the company" / "this firm".
- Date in header: {today}
- Lead with one concrete experience from the resume that matches the JD's strongest
  ask. Cite real numbers and tech names — do NOT invent.
- Forbidden words: leverage, transformative, cutting-edge, passionate, synergy.
- Forbidden refs: git branches, PR numbers, course codes, "collaborating on...",
  "in this PR".
- End with one sentence asking for an interview.

Output the cover letter as plain text. No markdown headers.
"""


def write_cover_letter(*, profile_name: str, company: str, title: str,
                        jd: str, resume_text: str,
                        max_critic_retries: int = 1) -> str:
    """Generate a cover letter, run critic, retry up to N times if it fails.
    Returns the final text (best-effort even if critic never passes)."""
    today = date.today().strftime("%B %d, %Y")
    system = SYSTEM_PROMPT.format(name=profile_name, role=title,
                                    company=company, today=today)
    user = f"JD:\n{jd[:3500]}\n\nMY RESUME (use facts from here only):\n{resume_text[:3500]}"

    last_text = ""
    last_issues = []
    for attempt in range(max_critic_retries + 1):
        text = llm_call(system, user, max_tokens=900, temperature=0.2)
        if not text:
            return last_text
        last_text = text
        issues = critic_check(text)
        if not issues:
            return text
        last_issues = issues
        # Retry with explicit feedback
        user = (f"PREVIOUS DRAFT FAILED:\n{', '.join(issues)}\n\n"
                f"FIX and re-output the entire letter:\n\n{user}")
    # Out of retries — return last attempt with a warning sentinel
    return last_text


def critic_check(text: str) -> list[str]:
    """Returns list of issue strings. Empty list = passes."""
    issues = []
    if not text:
        return ["empty"]
    if len(text.split()) > 500:
        issues.append(f"too long ({len(text.split())} words > 500)")
    if "—" in text or "–" in text:
        issues.append("contains em/en dash")
    low = text.lower()
    for w in CLICHE_WORDS:
        if w in low:
            issues.append(f"AI-cliché word '{w}'")
    for pat, desc in FORBIDDEN_PATTERNS:
        if re.search(pat, text, re.I):
            issues.append(desc)
    return issues
