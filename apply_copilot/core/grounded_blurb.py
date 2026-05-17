"""Generate a project blurb grounded in a single project's KB entry.

Used when an application question is clearly about one specific project
(e.g., "describe a project you've built that used Python"). The LLM is
asked to lift specific architecture facts, component names, and outcomes
directly from the KB — no generic paraphrase.

Two modes are detected from the employer's instruction:
- **project-intro**: lead with what the project IS + headline tech
- **fit-pitch**: lead with domain tie-in to the employer

Both modes follow the same writing rules: no em-dashes, no AI cliches,
no coursework / PR / branch refs.
"""
from __future__ import annotations
import re
from typing import Optional

from .llm_client import llm_call


SYSTEM_PROMPT = """You write a short custom blurb for a job application.

DETECT THE BLURB MODE from the employer's instruction:
- **PROJECT-INTRO mode**: employer asks for "a project you've built", "describe
  a project", "show us something real", "tell us about a project", "your most
  ambitious project". → INTRODUCE THE PROJECT (architecture, components,
  design decisions, outcomes). Do NOT force a domain tie-in to the employer's
  industry — the project introduction is what they want.
- **FIT-PITCH mode**: employer asks "why you're a fit", "what excites you
  about us", "tell us about yourself for this role". → Lead with domain
  tie-in to the employer + bridge from one of the candidate's projects.

You are given the FULL knowledge base of ONE specific project AND the
employer's instruction.

## PROJECT-INTRO mode rules

1. **Echo the JD anchor word.** If the employer asked for an "agent project",
   the blurb MUST include "agent" in the opening sentence. If "fine-tuning
   project" → "fine-tuning" appears.
2. **Sentence 1**: WHAT the project IS + headline TECH + WHO/WHAT it serves.
   Pattern: "I built [Project], a [one-line description] [powered by/using]
   [headline tech]".
3. **Sentences 2-4**: SPECIFIC architecture, component names, and design
   decisions lifted from the KB. Pick 3-4 of the most impressive specifics.
4. **Final sentence**: a concrete outcome or unique design choice. NOT
   "improves productivity". DO "system has run continuously for N days
   without manual restart", "processes thousands of events daily",
   "achieves <metric> on <benchmark>".
5. **No industry tie-in sentence in PROJECT-INTRO mode** — that's the cover
   letter's job.

## FIT-PITCH mode rules

1. Lead with what the candidate finds interesting about the employer's
   domain (one sentence).
2. Bridge to one of their projects with the most domain overlap (2-3
   sentences).
3. Close with what they'd contribute (1 sentence).

## Both modes: HARD WRITING RULES

- NEVER use em-dashes (—) or en-dashes (–). Use periods or commas.
- NEVER use AI-cliche phrases (leverage, delve, robust, cutting-edge, synergy,
  harness, passionate, transformative, embark, ever-evolving, in today's
  fast-paced).
- NEVER use bullet symbols (•, ·, +) in prose.
- NEVER write generic filler ("improves productivity", "organize data",
  "streamlines"). Every sentence must have at least one concrete technical
  detail from the KB.

HARD CONTENT RULE: every concrete claim must be traceable to a line in the
KB below. If the KB doesn't support a claim, do not make it.

FORBIDDEN PHRASES (recruiter-facing — read as student work log if used):
- github org/repo refs, PR numbers, branch names ("feat/...")
- coursework codes (E6792, Lab N, Assignment N), "for my class", "during my homework"
- process annotations ("Collaborating on...", "in this PR", "via the branch")
- internal artifacts (staging URLs, .zip dumps, bearer tokens)

Write architecture, flow, tradeoffs, outcomes — like a senior engineer's
project page, not a student annotating their commits.

Output: ONLY the blurb text. No JSON, no preamble, no markdown headers.
Just 3-5 sentences of plain prose."""


def _scrub(text: str) -> str:
    """Final-pass cleanup: kill em/en dashes and trim code fences."""
    out = text.strip()
    if out.startswith("```"):
        out = re.sub(r"^```[a-z]*\s*", "", out)
        out = out.rstrip("`").strip()
    out = out.replace("—", " - ").replace("–", "-")
    return out


def write_grounded_blurb(
    *,
    project_id: str,
    project_kb: str,
    jd: str = "",
    company: str = "",
    title: str = "",
    section_instruction: str,
) -> Optional[str]:
    """Generate a project-grounded blurb. Returns None on failure."""
    if not project_kb or not section_instruction:
        return None

    user = f"""COMPANY: {company}
TITLE: {title}
EMPLOYER INSTRUCTION (from the apply modal section):
{section_instruction}

JD (first 1500 chars for tone matching):
{jd[:1500]}

═══ PROJECT KB for `{project_id}` ═══
{project_kb}
═══ end KB ═══

Write the blurb now. 3-5 sentences. Specific facts only. No AI-tells."""

    raw = llm_call(SYSTEM_PROMPT, user, max_tokens=600, temperature=0.2)
    if not raw:
        return None
    return _scrub(raw) or None


def pick_project_for_question(
    *,
    question: str,
    project_kb: dict,
    jd: str = "",
) -> Optional[str]:
    """When the question doesn't name a project, score each KB entry by
    keyword overlap with the question + JD to pick the best match.
    """
    if not project_kb:
        return None
    q_low = (question or "").lower() + " " + (jd[:1000] or "").lower()
    if not q_low.strip():
        return next(iter(project_kb.keys()), None)
    best_id, best_score = None, 0
    for pid, content in project_kb.items():
        if not content:
            continue
        kb_low = content.lower()
        # Cheap scoring: count overlap of stem-ish tokens >= 4 chars
        tokens_q = set(re.findall(r"[a-z0-9]{4,}", q_low))
        tokens_k = set(re.findall(r"[a-z0-9]{4,}", kb_low))
        score = len(tokens_q & tokens_k)
        if score > best_score:
            best_id, best_score = pid, score
    return best_id or next(iter(project_kb.keys()), None)
