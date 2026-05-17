"""One-shot migration: SUBMITTED_LOG.md → SQLite Submission table.

The legacy autopilot wrote markdown blocks of the form:

    ### ✅ 2026-05-12 — Instalily (Software Engineer, 2026)
    - **Source**: ...
    - **URL**: https://...
    - **Resume**: `Foo_v2.pdf` (Agent base) — ...
    - **Status**: submitted | prep'd | external | gate_fail
    - **JD keywords**: a, b, c
    - **Notes**: ...

This script parses every `### ...` block and upserts a Submission row.
Existing rows (matched by URL + status='submitted') are skipped so re-runs
are idempotent.

Run:
    python -m apply_copilot.storage.migrate_log /path/to/SUBMITTED_LOG.md
"""
from __future__ import annotations
import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

from .db import get_session, init_db
from .models import Submission


# A submission block header. Real logs use four patterns:
#  1. `### ✅ 2026-05-12 — Company (Title)`            — emoji + ISO date
#  2. `### ⚠️ <date 待补> — Company (Title)`            — placeholder date
#  3. `### 📋 Company — Title`                          — backlog, no date / no parens
#  4. `### Company (Title) — 2026-05-12`               — reversed order
# Pattern 5 (`### 📞 YYYY-MM-DD — ...`) is a template line and is filtered out.
_EMOJI = r"[✅⛔🔌📝⏭❌🤔⚠📋📞🟡🟢🔴]️?"

HEADER_PATTERNS = [
    # 1 & 2: emoji + date + — + Company (Title)
    re.compile(
        rf"^###\s*(?:{_EMOJI}\s*)?"
        r"(?P<date>\d{4}-\d{2}-\d{2}|<[^>]+>)\s*[—–-]\s*"
        r"(?P<company>.+?)\s*\((?P<title>.+)\)\s*$"
    ),
    # 3: emoji + Company — Title (no parens, no date)
    re.compile(
        rf"^###\s*{_EMOJI}\s*"
        r"(?P<company>.+?)\s*[—–-]\s*(?P<title>[^—–\-]+?)\s*$"
    ),
    # 4: Company (Title) — date
    re.compile(
        r"^###\s*(?P<company>.+?)\s*\((?P<title>[^)]+)\)\s*[—–-]\s*"
        r"(?P<date>\d{4}-\d{2}-\d{2})\s*$"
    ),
]


def _match_header(line: str):
    if "YYYY-MM-DD" in line:  # template placeholder
        return None
    for pat in HEADER_PATTERNS:
        m = pat.match(line)
        if m:
            return m
    return None
FIELD_RE = re.compile(r"^-\s*\*\*(?P<key>[^*]+)\*\*\s*:\s*(?P<val>.+?)\s*$")
URL_RE = re.compile(r"https?://\S+")


def _slug(company: str, title: str) -> str:
    s = f"{company}__{title}".lower()
    s = re.sub(r"[^a-z0-9]+", "_", s).strip("_")
    return s[:80]


def parse_log(text: str) -> list[dict]:
    """Parse markdown log into a list of submission dicts."""
    blocks: list[dict] = []
    current: dict | None = None
    for line in text.splitlines():
        m = _match_header(line)
        if m:
            if current:
                blocks.append(current)
            raw_date = m.groupdict().get("date") or ""
            iso_date = raw_date if re.match(r"\d{4}-\d{2}-\d{2}", raw_date) else ""
            current = {
                "submitted_at": iso_date,
                "raw_date": raw_date,
                "company": m.group("company").strip(),
                "title": m.group("title").strip(),
                "url": "", "status": "submitted",
                "direction": "", "resume_filename": "", "notes": "",
                "platform": "handshake",
            }
            continue
        if current is None:
            continue
        fm = FIELD_RE.match(line)
        if not fm:
            continue
        key = fm.group("key").strip().lower()
        val = fm.group("val").strip()
        if key == "url":
            urls = URL_RE.findall(val)
            current["url"] = urls[0] if urls else val.strip("`")
        elif key == "status":
            low = val.lower()
            if "submitted" in low or "submit" in low:
                current["status"] = "submitted"
            elif "external" in low:
                current["status"] = "external_pending"
            elif "gate" in low or "fail" in low:
                current["status"] = "gate_fail"
            elif "withdraw" in low:
                current["status"] = "withdrawn"
            elif "prep" in low:
                current["status"] = "prepped"
        elif key == "resume":
            # e.g. `Foo_v2.pdf` (Agent base) — note
            rm = re.match(r"`([^`]+)`\s*(?:\(([^)]+)\))?", val)
            if rm:
                current["resume_filename"] = rm.group(1).strip()
                if rm.group(2):
                    current["direction"] = rm.group(2).strip().lower().split()[0]
        elif key in ("notes", "last follow-up"):
            current["notes"] = (current["notes"] + " | " + val).strip(" |")
        elif key == "source":
            if "handshake" in val.lower():
                current["platform"] = "handshake"
            elif "linkedin" in val.lower():
                current["platform"] = "linkedin"
            else:
                current["platform"] = "external"
    if current:
        blocks.append(current)
    return blocks


def import_to_sqlite(blocks: list[dict]) -> dict:
    """Idempotent upsert: skip rows with same URL + status=submitted."""
    init_db()
    added, skipped = 0, 0
    with get_session() as s:
        for b in blocks:
            if not b.get("company") or not b.get("title"):
                skipped += 1
                continue
            url = b.get("url") or ""
            if url:
                existing = s.query(Submission).filter_by(
                    url=url, status="submitted").first()
                if existing:
                    skipped += 1
                    continue
            iso = b.get("submitted_at") or ""
            try:
                dt = datetime.fromisoformat(iso) if iso else datetime.utcnow()
            except (ValueError, TypeError):
                dt = datetime.utcnow()
            slug = _slug(b["company"], b["title"])
            s.add(Submission(
                bundle_slug=slug, company=b["company"], title=b["title"],
                url=url, platform=b.get("platform", "handshake"),
                employment_type="intern",
                direction=b.get("direction", ""),
                resume_filename=b.get("resume_filename", ""),
                status=b.get("status", "submitted"),
                coverage_pct=0,
                submitted_at=dt,
                notes=b.get("notes", ""),
            ))
            added += 1
    return {"added": added, "skipped": skipped, "total": len(blocks)}


def main():
    parser = argparse.ArgumentParser(prog="apply_copilot.storage.migrate_log")
    parser.add_argument("path", help="Path to SUBMITTED_LOG.md")
    parser.add_argument("--dry-run", action="store_true",
                          help="Parse only; don't write to SQLite")
    args = parser.parse_args()

    p = Path(args.path).expanduser().resolve()
    if not p.exists():
        print(f"✗ {p} not found", file=sys.stderr)
        sys.exit(1)
    text = p.read_text(encoding="utf-8")
    blocks = parse_log(text)
    print(f"Parsed {len(blocks)} submission blocks from {p.name}")
    if args.dry_run:
        for b in blocks[:5]:
            print(f"  - {b['submitted_at']} | {b['company']} | "
                   f"{b['title']} | status={b['status']}")
        print(f"  ... ({len(blocks)} total)")
        return
    result = import_to_sqlite(blocks)
    print(f"✓ Added {result['added']}, skipped {result['skipped']} "
           f"(of {result['total']})")


if __name__ == "__main__":
    main()
