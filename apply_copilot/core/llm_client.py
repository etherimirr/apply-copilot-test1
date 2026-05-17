"""Thin OpenAI wrapper. Key from env var, models from config.
Deterministic (temperature=0) by default; per-call override allowed.
"""
from __future__ import annotations
import json
import os
import re
from typing import Optional

from ..config import OPENAI_API_KEY, OPENAI_MODEL_CHEAP, OPENAI_MODEL_STRONG


_client = None


def _get_client():
    global _client
    if _client is not None:
        return _client
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY env var not set")
    from openai import OpenAI
    _client = OpenAI(api_key=OPENAI_API_KEY)
    return _client


def llm_call(system: str, user: str, *, model: Optional[str] = None,
             max_tokens: int = 1500, temperature: float = 0.0) -> str:
    """Single chat completion. Returns the text content (or empty string on error)."""
    c = _get_client()
    mdl = model or OPENAI_MODEL_STRONG
    try:
        r = c.chat.completions.create(
            model=mdl,
            messages=[{"role": "system", "content": system},
                       {"role": "user", "content": user}],
            max_tokens=max_tokens, temperature=temperature,
        )
        return (r.choices[0].message.content or "").strip()
    except Exception as e:
        # Caller decides how to handle; we just surface empty.
        print(f"  [llm] {type(e).__name__}: {e}")
        return ""


def llm_call_mini(system: str, user: str, *, max_tokens: int = 1500,
                   temperature: float = 0.0) -> str:
    """gpt-4o-mini shortcut for cheap calls (audits, classification)."""
    return llm_call(system, user, model=OPENAI_MODEL_CHEAP,
                     max_tokens=max_tokens, temperature=temperature)


def parse_json_from_response(raw: str) -> dict:
    """LLM responses often wrap JSON in code fences or have trailing prose.
    Extract the first {...} block."""
    if not raw:
        return {}
    # Strip code fences
    raw = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.I)
    raw = re.sub(r"\s*```$", "", raw.strip())
    # Find the JSON object
    m = re.search(r"\{[\s\S]*\}", raw)
    if not m:
        return {}
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        # Try to fix common issues: trailing commas
        cleaned = re.sub(r",(\s*[}\]])", r"\1", m.group(0))
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            return {}
