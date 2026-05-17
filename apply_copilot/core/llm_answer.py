"""Generate answers for open-ended application questions.

Uses the user's profile, summary, and project_kb (uploaded markdown blobs)
as grounding. Persists every answer to qa_memory so the next near-identical
question is a free cache hit. Defaults to gpt-4o-mini for cost — open
questions are not coverage-critical like the resume audit.
"""
from __future__ import annotations
import re
from typing import Optional

from . import qa_memory
from .llm_client import llm_call_mini


def _project_kb_snippet(profile: dict, direction: str, max_chars: int = 2500) -> str:
    """Pull a few project blurbs from profile['project_kb'] (a dict of
    project_id -> markdown text). The user controls which projects exist
    by uploading via the dashboard.
    """
    kb = (profile or {}).get("project_kb") or {}
    if not kb:
        return ""
    # Priority order: any project_id starting with the direction, then the rest.
    keys = sorted(kb.keys(),
                   key=lambda k: (0 if direction and direction.split("_")[0] in k.lower() else 1,
                                  k))
    chunks: list[str] = []
    budget = max_chars
    for k in keys:
        txt = (kb.get(k) or "")[: max_chars // 2]
        if not txt:
            continue
        chunks.append(f"### {k}\n{txt}")
        budget -= len(txt)
        if budget < 200:
            break
    return "\n\n".join(chunks)


def _system_prompt(profile: dict) -> str:
    p = profile or {}
    name = (p.get("preferred_name") or p.get("first_name") or "the candidate").strip()
    school = p.get("school") or ""
    degree = p.get("school_degree") or ""
    major = p.get("school_major") or ""
    grad = p.get("graduation_date") or ""
    gpa = p.get("school_gpa") or ""
    summary = p.get("summary") or ""
    return f"""You are a job-application assistant writing in {name}'s voice.
Answer the employer's question with confidence, specificity, and grounding in
{name}'s real experience. NEVER invent companies, projects, numbers, or
credentials.

CANDIDATE SNAPSHOT:
- {school}, {degree} in {major} ({grad}), GPA {gpa}
- Summary: {summary[:400]}

RULES:
1. 80-180 words unless asked for "detailed" / "briefly".
2. Lead with concrete experience, not a topic sentence about being "passionate".
3. Plain language. No em dashes (—). Avoid AI-cliche words like "leverage",
   "transformative", "cutting-edge", "passionate about", "delve into".
4. For "Why this company / role" — name one specific thing about the role
   and tie it to one of the candidate's projects.
5. For "Tell us about yourself" — one paragraph version of the summary.
6. Short answer / yes-no — 1-2 sentences with one concrete example.
7. First person ("I", "my"), not third person.
"""


def answer_question(
    question: str,
    *,
    jd: str = "",
    company: str = "",
    title: str = "",
    direction: str = "",
    profile: Optional[dict] = None,
    save_to_memory: bool = True,
) -> str:
    """Return an answer string. Empty string on failure / unsupported."""
    if not question or len(question.strip()) < 5:
        return ""
    profile = profile or {}

    hit = qa_memory.lookup(question)
    if hit:
        return hit.get("a", "")

    kb_snippet = _project_kb_snippet(profile, direction)
    user = f"""COMPANY: {company}
ROLE: {title}

JD EXCERPT (may be empty):
{jd[:2000]}

CANDIDATE PROJECT NOTES:
{kb_snippet or '(no project notes uploaded)'}

EMPLOYER QUESTION:
{question}

Write the answer. Plain text, no markdown headers."""

    raw = llm_call_mini(_system_prompt(profile), user, max_tokens=600, temperature=0.3)
    ans = (raw or "").strip()
    ans = re.sub(r"^(answer:?\s*|response:?\s*)", "", ans, flags=re.I)
    ans = ans.strip('"').strip("'").strip()
    # No em / en dashes
    ans = ans.replace("—", " - ").replace("–", "-")
    if save_to_memory and ans:
        qa_memory.save(question, ans, company=company, source="llm_initial")
    return ans


def yes_no_for(question: str, profile: dict) -> Optional[str]:
    """Match common Y/N questions to a profile value or a safe default,
    without burning an LLM call. Returns 'Yes' / 'No' / None.
    """
    q = (question or "").lower()
    p = profile or {}
    if re.search(r"authoriz.*work.*u\.?s|legally.*authorized.*work|eligible to work", q):
        return p.get("work_auth_us", "Yes")
    if re.search(r"require.*sponsor|need.*sponsor|visa.*sponsor|h-?1b", q):
        return p.get("need_sponsorship", "No")
    if re.search(r"willing.*relocate|relocate.*willing", q):
        return p.get("willing_to_relocate", "Yes")
    if re.search(r"\b18 years?\b.*older|over 18|at least 18", q):
        return "Yes"
    if re.search(r"convicted.*felony|criminal.*record|background.*check.*concerns", q):
        return "No"
    if re.search(r"non[\s-]*compete|currently.*employ", q):
        return "No"
    return None
