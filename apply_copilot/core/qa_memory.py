"""Persistent Q&A memory — fuzzy matches prior answers to similar prompts.

Stored at QA_MEMORY_JSON (~/.apply_copilot/qa_memory.json).
Token-Jaccard with stopwords removed; threshold tunable.
"""
from __future__ import annotations
import json
import re
import time
from pathlib import Path
from typing import Optional

from ..config import QA_MEMORY_JSON


STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "of", "to", "in", "on", "at", "by", "for",
    "with", "as", "is", "are", "was", "were", "be", "been", "being",
    "do", "does", "did", "have", "has", "had",
    "you", "your", "yours", "we", "our", "us", "i", "me", "my",
    "this", "that", "these", "those", "it", "its",
    "what", "where", "when", "how", "why", "which", "who", "whom",
    "can", "could", "should", "would", "will", "may", "might",
    "any", "all", "some", "no", "not",
    "tell", "describe", "explain", "share", "give", "let",
    "please", "kindly", "yourself", "about",
    "now", "future", "currently",
    "if", "so",
}


def _normalize(s: str) -> str:
    s = (s or "").lower()
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _tokens(s: str) -> set[str]:
    return set(_normalize(s).split())


def _content_tokens(s: str) -> set[str]:
    return _tokens(s) - STOPWORDS


def _load() -> dict:
    if not QA_MEMORY_JSON.exists():
        return {"entries": []}
    try:
        return json.loads(QA_MEMORY_JSON.read_text(encoding="utf-8"))
    except Exception:
        return {"entries": []}


def _write(data: dict):
    QA_MEMORY_JSON.parent.mkdir(parents=True, exist_ok=True)
    QA_MEMORY_JSON.write_text(json.dumps(data, indent=2, ensure_ascii=False),
                               encoding="utf-8")


def lookup(question: str, min_similarity: float = 0.4) -> Optional[dict]:
    """Best matching prior entry above similarity threshold, or None.
    Side-effect: bumps `uses` + `lastUsed` on match.
    """
    if not question or len(question.strip()) < 5:
        return None
    data = _load()
    q_tokens = _content_tokens(question) or _tokens(question)
    if not q_tokens:
        return None
    best = None
    best_score = min_similarity
    for e in data.get("entries", []):
        prior = _content_tokens(e.get("q", "")) or _tokens(e.get("q", ""))
        if not prior:
            continue
        score = len(q_tokens & prior) / len(q_tokens | prior)
        if score > best_score:
            best_score, best = score, e
    if best:
        best["uses"] = (best.get("uses") or 0) + 1
        best["lastUsed"] = int(time.time())
        _write(data)
    return best


def save(question: str, answer: str, tags: Optional[list[str]] = None,
         company: str = "", source: str = "") -> dict:
    """Append (or replace near-exact) a Q&A entry."""
    if not question or not answer:
        return {}
    data = _load()
    entries = data.get("entries", [])
    q_tokens = _content_tokens(question) or _tokens(question)
    for e in entries:
        prior = _content_tokens(e.get("q", "")) or _tokens(e.get("q", ""))
        if not prior or not q_tokens:
            continue
        sim = len(q_tokens & prior) / len(q_tokens | prior)
        if sim > 0.9:  # essentially the same question
            e["a"] = answer
            e["lastUpdated"] = int(time.time())
            e["uses"] = (e.get("uses") or 0) + 1
            _write({"entries": entries})
            return e
    new = {
        "q": question.strip(), "a": answer.strip(),
        "tags": tags or [], "company": company, "source": source,
        "ts": int(time.time()), "lastUpdated": int(time.time()), "uses": 1,
    }
    entries.append(new)
    _write({"entries": entries})
    return new


def all_entries() -> list[dict]:
    return _load().get("entries", [])
