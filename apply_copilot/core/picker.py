"""LLM picks which user-uploaded resume direction best fits a given JD.

Returns one of the user's RESUME_DIRECTIONS, or "__skip__:<reason>" if the
role is clearly off-fit (PM / hardware / marketing / etc).
"""
from __future__ import annotations
from .llm_client import llm_call_mini, parse_json_from_response
from ..config import RESUME_DIRECTIONS


SYSTEM = """You're a job-fit classifier for a software engineer applying via
an automated tool. Given a JD, decide:

1. Is this role a clear off-fit (Product Manager, hardware-only, designer, marketing,
   HR, finance analyst, accounting)? → action: "skip"
2. Otherwise pick the best matching resume direction from the user's library:

DIRECTIONS:
- mle: machine learning / data / applied ML
- agent: AI agents, LLM apps, multi-agent systems
- sde_general: backend, full-stack, infra, general SWE
- sde_dl: SDE roles with deep-learning / GPU / compiler / systems angle
- default: catch-all, use if none of the above strongly fits

Output JSON only:
{"action": "apply" | "skip", "direction": "mle|agent|sde_general|sde_dl|default",
 "confidence": "high|medium|low", "reason": "<one short sentence>"}
"""


def pick_direction(jd: str, title: str, company: str,
                    available_directions: list[str] = None) -> dict:
    """Returns a dict {action, direction, confidence, reason}.

    Caller checks action — if "skip", don't run the rest of the pipeline.
    """
    user = f"COMPANY: {company}\nTITLE: {title}\n\nJD:\n{jd[:2500]}"
    raw = llm_call_mini(SYSTEM, user, max_tokens=200)
    d = parse_json_from_response(raw)
    action = (d.get("action") or "apply").lower()
    direction = (d.get("direction") or "default").lower()
    # Coerce to a known direction; fall back to "default"
    avail = available_directions or RESUME_DIRECTIONS
    if direction not in avail:
        direction = "default" if "default" in avail else avail[0] if avail else "default"
    return {
        "action": action,
        "direction": direction,
        "confidence": (d.get("confidence") or "").lower(),
        "reason": d.get("reason", "")[:200],
    }
