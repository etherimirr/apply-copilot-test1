"""Audit resume text against a JD.

Pipeline:
1. extract_jd_keywords(jd) — pull every relevant keyword from JD
2. classify_against_resume(keywords, resume_text) — explicit | implicit | missing
3. compute coverage (raw + addressable)

LLM cost: ~$0.03 for extract (gpt-4o, exhaustive) + ~$0.003 for classify (mini).
"""
from __future__ import annotations
from typing import Optional
from .llm_client import llm_call, llm_call_mini, parse_json_from_response


EXTRACT_SYSTEM = """Extract every keyword/skill from a JD that a resume should
cover. A typical JD has 15-30 extractable keywords. Be exhaustive.

Categories to look for:
- Programming languages, frameworks, libraries
- Infra / cloud / databases / queues / observability
- ML / AI concepts (RAG, agents, fine-tuning, evals, etc)
- Tools (Docker, K8s, AWS, etc)
- Domain (healthcare, finance, robotics, etc)
- Process (Agile, CI/CD, code review)
- Specific products / inputs / outputs the JD mentions

Output JSON only:
{"keywords": [{"keyword": "Python", "importance": "high|med|low",
                "type": "lang|framework|tool|concept|domain|process"}]}
"""


CLASSIFY_SYSTEM = """Given KEYWORDS and a RESUME TEXT, classify each keyword:
- "explicit": the keyword (or a very close synonym) appears verbatim in resume
- "implicit": the resume describes work that semantically covers this keyword
- "missing": neither explicit nor implicit; the resume doesn't cover it
- "no_fix": missing AND can't reasonably be added (industry-specific to a domain
  the candidate has zero experience in — e.g. asking for "Solana smart contracts"
  when the resume has no blockchain work)

For each missing keyword, suggest one fix:
- "skills_add:<category>:<keyword>" — append to Skills section under that category
- "bullet_inject:<anchor>:<keyword>" — add to an existing bullet starting with <anchor>
- "project_swap:<project_id>" — swap a project in for one that covers this

Output JSON only:
{"explicit": [{"keyword": "X", "evidence_line": "..."}],
 "implicit": [{"keyword": "X", "implicit_via": "..."}],
 "missing": [{"keyword": "X", "type": "...", "importance": "...",
                "suggested_fix": "...", "no_fix": true|false}],
 "coverage_pct": <0-100>,
 "addressable_coverage_pct": <0-100>}
"""


def extract_jd_keywords(jd: str, title: str = "", company: str = "") -> list[dict]:
    """Returns list of {keyword, importance, type}."""
    user = f"COMPANY: {company}\nTITLE: {title}\n\nJD:\n{jd[:5000]}"
    raw = llm_call(EXTRACT_SYSTEM, user, max_tokens=1500)
    return parse_json_from_response(raw).get("keywords", []) or []


def classify_against_resume(keywords: list[dict], resume_text: str) -> dict:
    """Classify each keyword as explicit/implicit/missing. Returns full audit dict.
    Uses gpt-4o-mini for cost (this is the high-frequency call).
    """
    import json
    user = (f"KEYWORDS:\n{json.dumps(keywords, ensure_ascii=False, indent=2)}\n\n"
            f"RESUME TEXT:\n{resume_text[:5000]}")
    raw = llm_call_mini(CLASSIFY_SYSTEM, user, max_tokens=2500)
    result = parse_json_from_response(raw)
    # Ensure shape
    result.setdefault("explicit", [])
    result.setdefault("implicit", [])
    result.setdefault("missing", [])
    result.setdefault("coverage_pct", _compute_raw_coverage(result, keywords))
    result.setdefault("addressable_coverage_pct",
                      _compute_addressable_coverage(result, keywords))
    return result


def _compute_raw_coverage(cls_result: dict, keywords: list[dict]) -> int:
    if not keywords:
        return 0
    covered = len(cls_result.get("explicit", [])) + len(cls_result.get("implicit", []))
    return round(100 * covered / len(keywords))


def _compute_addressable_coverage(cls_result: dict, keywords: list[dict]) -> int:
    """Addressable = exclude 'no_fix' keywords from denominator."""
    if not keywords:
        return 0
    no_fix = sum(1 for m in cls_result.get("missing", []) if m.get("no_fix"))
    addressable = max(1, len(keywords) - no_fix)
    covered = len(cls_result.get("explicit", [])) + len(cls_result.get("implicit", []))
    # Safety: a single match counted as addressable=1 will return 100% trivially
    # — Christina hit this bug at low explicit coverage with high "no_fix". Add
    # a coverage_pct floor of 30% to prevent that, mirroring the bug fix from
    # the local autopilot.
    pct = round(100 * covered / addressable)
    raw_pct = _compute_raw_coverage(cls_result, keywords)
    if raw_pct < 30 and pct > 80:
        # Suspicious: too few real hits, too many no_fix. Trust the raw number.
        return raw_pct
    return pct
