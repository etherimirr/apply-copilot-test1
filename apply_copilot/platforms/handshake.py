"""Handshake autopilot — discover postings + auto-apply via Playwright.

Adapted from the local _autopilot.py to use the SaaS infrastructure:
  - Reads resumes from RESUMES_DIR (user-uploaded), keyed by direction
  - Writes submission events to SQLite (Submission table), not SUBMITTED_LOG.md
  - Loads user profile from SQLite (Profile table)
  - LLM calls go through apply_copilot.core.llm_client (env API key)

CLI:
    python -m apply_copilot.platforms.handshake \\
        --max 500 \\
        --sort newest \\
        --employment-type intern \\
        --external-mode skip
"""
from __future__ import annotations
import argparse
import asyncio
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from playwright.async_api import async_playwright, Page, TimeoutError as PWTimeoutError

from ..config import (
    BROWSER_PROFILE, GENERATED_DIR, RESUMES_DIR, LOGS_DIR,
    AUTO_SUBMIT_MIN_COVERAGE, MAX_RESUME_PAGES, OPENAI_API_KEY,
    pdf_to_text, ensure_dirs,
)
from ..storage import init_db, get_session, Profile, Resume, Submission, BundleState
from ..core import picker, audit, resume_editor, cl_writer
from ..core.eligibility import disqualifier
from .ats.detect import detect_ats
from .ats.filler import fill_application
from .ats.workday import workday_run_to_submit


HANDSHAKE_URL = "https://app.joinhandshake.com/job-search"


# ───────────────────────────────────────────────────────────────────────────
# Logging
# ───────────────────────────────────────────────────────────────────────────

def log(msg: str):
    """Print + tee to a per-run log file."""
    print(msg, flush=True)


# ───────────────────────────────────────────────────────────────────────────
# Profile / Resume access (SQLite-backed)
# ───────────────────────────────────────────────────────────────────────────

def load_user_profile() -> dict:
    with get_session() as s:
        p = s.get(Profile, 1)
        if not p:
            return {}
        # Convert to plain dict — same shape as the local profile.json
        return {
            "fullName": f"{p.first_name} {p.last_name}".strip() or "Applicant",
            "firstName": p.first_name, "lastName": p.last_name,
            "email": p.email, "phone": p.phone,
            "linkedin": p.linkedin, "github": p.github,
            "school": p.school, "schoolDegree": p.school_degree,
            "schoolMajor": p.school_major, "schoolGPA": p.school_gpa,
            "graduationDate": p.graduation_date,
            "workAuthUS": p.work_auth_us, "needSponsorship": p.need_sponsorship,
            "summary": p.summary, "gender": p.gender, "race": p.race,
        }


def resolve_resume_path(direction: str) -> Optional[Path]:
    """Find the user-uploaded resume for this direction. Falls back to default
    or first uploaded resume.
    """
    with get_session() as s:
        # exact direction
        r = s.query(Resume).filter_by(direction=direction).first()
        if r:
            return RESUMES_DIR / r.filename
        # default
        r = s.query(Resume).filter_by(is_default=True).first()
        if r:
            return RESUMES_DIR / r.filename
        # any
        r = s.query(Resume).first()
        return (RESUMES_DIR / r.filename) if r else None


# ───────────────────────────────────────────────────────────────────────────
# Discovery: pill activation + sort + pagination
# ───────────────────────────────────────────────────────────────────────────

PILL_LABEL = {"intern": "Internship", "fulltime": "Full-time job"}
SORT_LABEL = {
    "newest": "Newest",
    "most_relevant": "Most relevant",
    "soonest_deadline": "Soonest application deadlines",
}


async def _read_jobs_found(page: Page) -> int:
    """Read the 'X jobs found' header. Returns 0 if missing.
    Handles formats like '2,387 jobs found' and '10K+ jobs found'.
    """
    text = await page.evaluate("""
        () => {
            for (const el of document.querySelectorAll('*')) {
                if (el.children.length > 1) continue;
                const t = (el.textContent || '').trim();
                if (/^[\\d,KkMm+\\s]+jobs?\\s+found$/i.test(t) && t.length < 40) return t;
            }
            return '';
        }
    """) or ""
    m = re.match(r"^([\d,]+)(K\+?|M\+?)?", text.strip(), re.I)
    if not m:
        return 0
    n = int(m.group(1).replace(",", ""))
    suf = (m.group(2) or "").upper()
    if suf.startswith("K"): n *= 1000
    elif suf.startswith("M"): n *= 1_000_000
    return n


async def _click_pill(page: Page, label: str) -> bool:
    """Activate an employment-type filter pill (e.g. 'Internship')."""
    selectors = [
        f'.PillCheck:has-text("{label}")',
        f'label:has-text("{label}"):not(:has-text("{label}s"))',
        f'[class*="PillCheck"]:has-text("{label}")',
        f'div:text-is("{label}")',
    ]
    pre = await _read_jobs_found(page)
    for sel in selectors:
        try:
            pill = page.locator(sel).first
            if await pill.count() == 0:
                continue
            await pill.scroll_into_view_if_needed(timeout=2000)
            await pill.click(timeout=4000, force=True)
            await page.wait_for_timeout(3000)
            post = await _read_jobs_found(page)
            if post > 100 and (pre == 0 or post < pre):
                return True
        except Exception:
            pass
    return False


async def _switch_sort(page: Page, sort_key: str) -> bool:
    target = SORT_LABEL.get(sort_key)
    if not target or sort_key == "most_relevant":
        return True  # default
    try:
        combo = page.locator('[role="combobox"]').filter(
            has_text=re.compile(r"(Most relevant|Newest|Soonest)", re.I)).first
        if await combo.count() == 0:
            return False
        await combo.click(timeout=4000)
        await page.wait_for_timeout(1000)
        for sel in [f'[role="option"]:has-text("{target}")',
                    f'li:has-text("{target}")']:
            opt = page.locator(sel).first
            if await opt.count() > 0:
                await opt.click(timeout=3000)
                await page.wait_for_timeout(2500)
                return True
    except Exception:
        pass
    return False


async def scrape_handshake(page: Page, employment_type: str, sort_key: str,
                              max_pages: int = 100) -> list[dict]:
    """Navigate, activate pill + sort, paginate, return candidate list."""
    await page.goto(HANDSHAKE_URL, wait_until="domcontentloaded", timeout=30000)
    await page.wait_for_timeout(4000)
    pre_count = await _read_jobs_found(page)
    log(f"  Handshake: pre-filter {pre_count} jobs")
    if pre_count == 0 or pre_count > 5000:
        if await _click_pill(page, PILL_LABEL.get(employment_type, "Internship")):
            log(f"  ✓ activated pill: {PILL_LABEL.get(employment_type)}")
    if await _switch_sort(page, sort_key):
        log(f"  ✓ sort: {SORT_LABEL.get(sort_key, sort_key)}")
    # Paginate
    all_cards = {}
    for page_idx in range(1, max_pages + 1):
        cards = await page.evaluate("""
            () => {
                const links = document.querySelectorAll('a[href*="/job-search/"]');
                const seen = new Set();
                const out = [];
                for (const a of links) {
                    const m = a.href.match(/\\/job-search\\/(\\d+)/);
                    if (!m || seen.has(m[1])) continue;
                    seen.add(m[1]);
                    let card = a;
                    for (let i = 0; i < 6 && card; i++) {
                        if (card.innerText && card.innerText.length > 40) break;
                        card = card.parentElement;
                    }
                    const txt = (card?.innerText || '').slice(0, 280);
                    out.push({id: m[1], text: txt});
                }
                return out;
            }
        """)
        new_count = 0
        for c in cards:
            if c["id"] in all_cards:
                continue
            all_cards[c["id"]] = c
            new_count += 1
        log(f"    page {page_idx}: +{new_count} (total {len(all_cards)})")
        if new_count == 0:
            break
        # Next page via numbered button / Next
        clicked = False
        target = str(page_idx + 1)
        for sel in [f'button[aria-label="Page {target}"]',
                    f'button:text-is("{target}")',
                    'button[aria-label="Next page"]', 'button:has-text("Next")']:
            try:
                btn = page.locator(sel).first
                if await btn.count() == 0:
                    continue
                if (await btn.get_attribute("aria-disabled")) == "true":
                    continue
                await btn.scroll_into_view_if_needed(timeout=2000)
                await btn.click(timeout=4000)
                clicked = True
                break
            except Exception:
                continue
        if not clicked:
            break
        await page.wait_for_timeout(4500)

    # Parse each card → {id, company, title, url}
    parsed = []
    for c in all_cards.values():
        lines = [l.strip() for l in (c.get("text") or "").split("\n") if l.strip()]
        if len(lines) < 2:
            continue
        company, title = lines[0], lines[1]
        full = c["text"].lower()
        if "full-time" in full and "intern" not in title.lower() and "promoted" in full:
            continue
        parsed.append({"id": c["id"], "company": company, "title": title,
                        "url": f"https://app.joinhandshake.com/jobs/{c['id']}",
                        "employment_type": employment_type})
    return parsed


# ───────────────────────────────────────────────────────────────────────────
# Pre-flight + JD scrape
# ───────────────────────────────────────────────────────────────────────────

async def _scrape_jd_body(page: Page, url: str) -> str:
    await page.goto(url, wait_until="domcontentloaded", timeout=30000)
    await page.wait_for_timeout(2200)
    # Click any "More" / "Show more" to expand
    for sel in ['button:has-text("Show more")', 'button:has-text("Read more")',
                'button:has-text("More")', 'a:has-text("Show more")',
                'span:has-text("...More")', 'span:has-text("…More")']:
        try:
            more = page.locator(sel).first
            if await more.count() > 0:
                await more.click(timeout=1500, force=True)
                await page.wait_for_timeout(300)
                break
        except Exception:
            pass
    return await page.evaluate("""
        () => {
            const txt = document.body.innerText;
            const i = txt.indexOf('Job description');
            if (i < 0) return txt.slice(0, 6000);
            const j = txt.indexOf('About the employer', i);
            return txt.slice(0, j > 0 ? j : Math.min(i + 8000, txt.length));
        }
    """) or ""


async def _check_external(page: Page) -> str:
    """Return 'native' if standard Apply button visible, 'external' if only
    Apply externally, 'unknown' otherwise."""
    try:
        native = page.locator('button:has-text("Apply"):not(:has-text("externally"))').first
        if await native.count() > 0:
            return "native"
        ext = page.locator('button:has-text("Apply externally")').first
        if await ext.count() > 0:
            return "external"
    except Exception:
        pass
    return "unknown"


# ───────────────────────────────────────────────────────────────────────────
# Apply: open modal, upload files, click Submit
# ───────────────────────────────────────────────────────────────────────────

async def _scrape_modal_sections(page: Page) -> list[dict]:
    """Scrape the Handshake apply modal sections: heading, instruction, file input name."""
    return await page.evaluate("""
        () => {
            const dialogs = Array.from(document.querySelectorAll('[role="dialog"], [aria-modal="true"]'));
            let modal = null;
            for (const d of dialogs) {
                const t = (d.textContent || '').toLowerCase();
                if (t.includes('apply to ') || t.includes('attach your resume')) {
                    modal = d; break;
                }
            }
            if (!modal) modal = document.body;
            const anchors = Array.from(modal.querySelectorAll('*')).filter(el => {
                if (el.children.length > 2) return false;
                const t = (el.textContent || '').trim();
                return t && t.length < 100 &&
                       /^attach (your|other)|^step \\d+:|instructions from employer/i.test(t);
            });
            const seen = new Set();
            const out = [];
            for (const h of anchors) {
                const heading = (h.textContent || '').trim();
                if (seen.has(heading)) continue;
                seen.add(heading);
                let container = h;
                for (let i = 0; i < 4 && container.parentElement; i++) {
                    if (container.parentElement.children.length > 1) {
                        container = container.parentElement; break;
                    }
                    container = container.parentElement;
                }
                const fi = container.querySelector('input[type="file"]');
                out.push({heading, fileInputName: fi ? fi.name : null});
            }
            return out;
        }
    """)


async def _remove_default_chip(page: Page) -> Optional[str]:
    """Click the X on the pre-selected default resume chip. Returns the filename
    that was removed, or None."""
    try:
        current = await page.evaluate("""
            () => {
                const all = Array.from(document.querySelectorAll('*')).filter(el => el.children.length === 0);
                const t = all.find(el => /\\.pdf$|\\.docx$/i.test((el.textContent || '').trim()));
                return t ? t.textContent.trim() : null;
            }
        """)
        if not current:
            return None
        clicked = await page.evaluate("""
            (filename) => {
                const all = Array.from(document.querySelectorAll('*')).filter(el => el.children.length === 0);
                const t = all.find(el => (el.textContent || '').trim() === filename);
                if (!t) return false;
                let p = t;
                for (let i = 0; i < 6 && p; i++) {
                    const btn = p.querySelector('button');
                    if (btn) { btn.click(); return true; }
                    p = p.parentElement;
                }
                return false;
            }
        """, current)
        if clicked:
            await page.wait_for_timeout(1500)
            return current
    except Exception:
        pass
    return None


async def submit_application(page: Page, *, url: str, company: str, title: str,
                                resume_pdf: Path, cover_letter_pdf: Optional[Path] = None,
                                ) -> dict:
    """Open Apply modal, upload files, click Submit. Returns
    {ok, reason, label}."""
    await page.goto(url, wait_until="domcontentloaded", timeout=30000)
    # Find native Apply button
    try:
        apply_btn = page.locator(
            'button:has-text("Apply"):not(:has-text("externally"))').first
        await apply_btn.wait_for(timeout=10000)
    except PWTimeoutError:
        return {"ok": False, "reason": "no Apply button (likely external apply)"}
    # Click + wait for modal
    modal_sel = ('[role="dialog"]:has-text("Apply to"), '
                  '[role="dialog"]:has-text("Attach"), '
                  '[role="dialog"]:has-text("Submit Documents")')
    opened = False
    for attempt in range(3):
        try:
            await apply_btn.scroll_into_view_if_needed(timeout=2000)
            await apply_btn.click(timeout=4000)
            try:
                await page.locator(modal_sel).first.wait_for(timeout=8000)
                opened = True
                break
            except PWTimeoutError:
                await page.wait_for_timeout(1500)
        except Exception:
            await page.wait_for_timeout(1500)
    if not opened:
        return {"ok": False, "reason": "Apply modal didn't open"}

    sections = await _scrape_modal_sections(page)
    log(f"    modal sections: {len(sections)}")

    # Upload non-resume sections
    for s in sections:
        heading = (s.get("heading") or "").lower()
        fi = s.get("fileInputName")
        if not fi or "resume" in heading:
            continue
        chosen = None
        if "cover" in heading and cover_letter_pdf and cover_letter_pdf.exists():
            chosen = cover_letter_pdf
        if chosen:
            try:
                await page.locator(f'input[name="{fi}"]').first.set_input_files(str(chosen))
            except Exception:
                pass

    # Resume: remove default chip, then upload
    await _remove_default_chip(page)
    try:
        await page.locator('input[name="file-Resume"]').first.set_input_files(
            str(resume_pdf), timeout=10000)
    except Exception:
        # Fallback: any input[type=file]
        try:
            inputs = await page.locator('input[type="file"]').all()
            uploaded = False
            for inp in inputs:
                try:
                    await inp.set_input_files(str(resume_pdf))
                    uploaded = True
                    break
                except Exception:
                    continue
            if not uploaded:
                return {"ok": False, "reason": "resume upload failed via all paths"}
        except Exception as e:
            return {"ok": False, "reason": f"resume upload error: {e}"}

    # Click Submit
    await page.wait_for_timeout(2000)
    submit_locators = [
        'button:has-text("Submit Application")',
        'button:has-text("Submit")',
        'button[type="submit"]',
    ]
    for sel in submit_locators:
        try:
            btn = page.locator(sel).first
            if await btn.count() == 0:
                continue
            await btn.click(timeout=4000)
            await page.wait_for_timeout(3000)
            return {"ok": True, "label": "Submit Application"}
        except Exception:
            continue
    return {"ok": False, "reason": "Submit button not found"}


# ───────────────────────────────────────────────────────────────────────────
# Per-job pipeline
# ───────────────────────────────────────────────────────────────────────────

def _bundle_slug(company: str, title: str) -> str:
    co = re.sub(r"[^a-zA-Z0-9]+", "_", company or "App").strip("_")[:40] or "Co"
    tt = re.sub(r"[^a-zA-Z0-9]+", "_", title or "Role").strip("_")[:50] or "Role"
    return f"{co}__{tt}"


def _already_submitted(url: str) -> bool:
    with get_session() as s:
        return s.query(Submission).filter_by(url=url, status="submitted").count() > 0


def _record_submission(*, bundle_slug: str, company: str, title: str, url: str,
                          employment_type: str, direction: str,
                          resume_filename: str, status: str, coverage_pct: int,
                          notes: str = ""):
    with get_session() as s:
        s.add(Submission(
            bundle_slug=bundle_slug, company=company, title=title, url=url,
            platform="handshake", employment_type=employment_type,
            direction=direction, resume_filename=resume_filename,
            status=status, coverage_pct=coverage_pct, notes=notes,
        ))


async def process_one(page: Page, c: dict, profile: dict, employment_type: str,
                         submit: bool = True, external_mode: str = "skip") -> dict:
    """Discover → pre-flight → prep → submit one candidate.

    external_mode controls what happens when only an "Apply externally" button
    is present: "skip" (default, fastest), "fill" (open + auto-fill, leave
    open for user review), "fill-submit" (NOT recommended).
    """
    url, company, title = c["url"], c["company"], c["title"]
    slug = _bundle_slug(company, title)

    if _already_submitted(url):
        return {"action": "skip", "reason": "already submitted"}

    # 1. Scrape JD
    try:
        jd = await _scrape_jd_body(page, url)
    except Exception as e:
        return {"action": "error", "reason": f"jd scrape failed: {e}"}
    if len(jd) < 300:
        return {"action": "skip", "reason": "JD too short"}

    # 2. Pre-flight: eligibility regex
    dq = disqualifier(jd)
    if dq:
        _record_submission(bundle_slug=slug, company=company, title=title, url=url,
                           employment_type=employment_type, direction="",
                           resume_filename="", status="skipped_eligibility",
                           coverage_pct=0)
        return {"action": "skip", "reason": f"eligibility: {dq}"}

    # 3. Pre-flight: external probe
    ext = await _check_external(page)
    if ext == "external":
        if external_mode == "skip":
            _record_submission(bundle_slug=slug, company=company, title=title, url=url,
                               employment_type=employment_type, direction="",
                               resume_filename="", status="external_pending",
                               coverage_pct=0)
            return {"action": "skip", "reason": "external apply only"}
        # external_mode in {"fill", "fill-submit"} — open the external page and
        # auto-fill it. We still pick a resume direction so the right file
        # gets uploaded.
        return await _handle_external_apply(
            page, profile=profile, slug=slug, company=company, title=title,
            url=url, jd=jd, employment_type=employment_type,
            submit_after_fill=(external_mode == "fill-submit"),
        )

    # 4. Picker — pick direction or skip
    p = picker.pick_direction(jd, title, company)
    if p["action"] == "skip":
        _record_submission(bundle_slug=slug, company=company, title=title, url=url,
                           employment_type=employment_type, direction="",
                           resume_filename="", status="picker_skip",
                           coverage_pct=0)
        return {"action": "skip", "reason": f"picker: {p['reason']}"}
    direction = p["direction"]

    # 5. Find user's resume for this direction
    resume_path = resolve_resume_path(direction)
    if not resume_path or not resume_path.exists():
        return {"action": "error",
                "reason": f"no resume uploaded for direction '{direction}' (upload via dashboard)"}

    # 6. Audit JD vs resume
    doc = resume_editor.load_docx(resume_path)
    resume_text = resume_editor.docx_to_text(doc)
    keywords = audit.extract_jd_keywords(jd, title, company)
    audit_result = audit.classify_against_resume(keywords, resume_text)
    addressable = audit_result.get("addressable_coverage_pct", 0)

    # 7. Apply edits (skills_add / bullet_inject) with page-count guard
    out_pdf = GENERATED_DIR / f"{slug}_resume.pdf"
    edits = []
    for m in (audit_result.get("missing") or [])[:8]:
        fix = (m.get("suggested_fix") or "")
        if fix.startswith("skills_add:"):
            parts = fix.split(":", 2)
            if len(parts) == 3:
                edits.append({"type": "skills_add", "category": parts[1].strip(),
                              "keywords": [parts[2].strip()]})
        elif fix.startswith("bullet_inject:"):
            parts = fix.split(":", 2)
            if len(parts) == 3:
                edits.append({"type": "bullet_inject", "anchor": parts[1].strip(),
                              "addition": parts[2].strip()})
    edit_result = resume_editor.apply_edits_with_rollback(doc, edits, out_pdf)
    final_pdf = edit_result.get("pdf_path") or out_pdf

    # 8. Re-audit on edited resume
    new_resume_text = resume_editor.docx_to_text(doc)
    audit2 = audit.classify_against_resume(keywords, new_resume_text)
    final_pct = audit2.get("addressable_coverage_pct", 0)

    if final_pct < AUTO_SUBMIT_MIN_COVERAGE:
        _record_submission(bundle_slug=slug, company=company, title=title, url=url,
                           employment_type=employment_type, direction=direction,
                           resume_filename=resume_path.name, status="gate_fail",
                           coverage_pct=final_pct)
        return {"action": "skip",
                "reason": f"gate fail: {final_pct}% < {AUTO_SUBMIT_MIN_COVERAGE}%"}

    # 9. CL
    cl_text = cl_writer.write_cover_letter(
        profile_name=profile.get("fullName", "Applicant"),
        company=company, title=title, jd=jd, resume_text=new_resume_text,
    )
    cl_pdf = None
    if cl_text:
        # Render CL as a simple PDF (reportlab) — preserves the plain
        # style: Times New Roman 10pt, single page
        cl_pdf = GENERATED_DIR / f"{slug}_cover_letter.pdf"
        _render_cl_to_pdf(cl_text, cl_pdf, who=profile.get("fullName", ""))

    # 10. Submit
    if not submit:
        return {"action": "skipped_dry_run", "coverage": final_pct}
    r = await submit_application(page, url=url, company=company, title=title,
                                    resume_pdf=final_pdf, cover_letter_pdf=cl_pdf)
    if r["ok"]:
        _record_submission(bundle_slug=slug, company=company, title=title, url=url,
                           employment_type=employment_type, direction=direction,
                           resume_filename=resume_path.name, status="submitted",
                           coverage_pct=final_pct)
        return {"action": "submitted", "coverage": final_pct}
    else:
        return {"action": "error", "reason": r.get("reason", "submit failed")}


async def _handle_external_apply(page: Page, *, profile: dict, slug: str,
                                    company: str, title: str, url: str, jd: str,
                                    employment_type: str,
                                    submit_after_fill: bool = False) -> dict:
    """external_mode != "skip": click "Apply externally", wait for new tab,
    pick a resume direction so the right file gets attached, then run the
    generic filler. Leaves the tab open for user review unless submit_after_fill.
    """
    ctx = page.context
    try:
        async with ctx.expect_page(timeout=15000) as new_page_info:
            await page.locator('button:has-text("Apply externally")').first.click(timeout=5000)
        ext_page = await new_page_info.value
    except Exception as e:
        return {"action": "skip", "reason": f"could not open external page: {e}"}

    try:
        await ext_page.wait_for_load_state("domcontentloaded", timeout=20000)
    except Exception:
        pass

    # Pick direction + resolve resume so the file uploads correctly
    p = picker.pick_direction(jd, title, company)
    direction = p.get("direction") if p.get("action") != "skip" else "default"
    resume_path = resolve_resume_path(direction or "default")

    ats = detect_ats(ext_page.url)
    try:
        if ats == "workday":
            wd = await workday_run_to_submit(
                ext_page, profile, jd=jd, company=company, title=title,
                direction=direction or "", resume_path=resume_path,
            )
            # Aggregate filled-fields count across steps for the notes column
            total_filled = sum(len(r.get("filled", [])) for r in wd.get("results", []))
            total_open_qs = sum(len(r.get("open_questions", [])) for r in wd.get("results", []))
            total_unclassified = sum(len(r.get("unclassified", [])) for r in wd.get("results", []))
            report = {
                "ok": wd.get("ok", False),
                "ats": ats,
                "submitted": False,  # Workday handler never clicks final Submit
                "filled": [f"step_total={total_filled}"],
                "open_questions": [{"steps": total_open_qs}],
                "unclassified": [f"step_total={total_unclassified}"],
                "workday_steps": wd.get("steps"),
                "workday_stopped_at": wd.get("stopped_at"),
            }
        else:
            report = await fill_application(
                ext_page, profile,
                direction=direction or "",
                jd=jd, company=company, title=title,
                resume_path=resume_path,
                submit=submit_after_fill,
            )
    except Exception as e:
        return {"action": "error", "reason": f"filler crashed: {type(e).__name__}: {e}"}

    status = "submitted" if report.get("submitted") else "external_filled"
    _record_submission(bundle_slug=slug, company=company, title=title, url=url,
                       employment_type=employment_type,
                       direction=direction or "",
                       resume_filename=(resume_path.name if resume_path else ""),
                       status=status, coverage_pct=0,
                       notes=f"filled={len(report.get('filled', []))}, "
                              f"open_qs={len(report.get('open_questions', []))}, "
                              f"unclassified={len(report.get('unclassified', []))}")
    return {"action": status, "report": report}


def _render_cl_to_pdf(text: str, out_path: Path, who: str = ""):
    """Render the cover letter text as a simple 1-page PDF.
    Uses reportlab for portability (no LibreOffice needed)."""
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
    from reportlab.lib.units import inch
    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(str(out_path), pagesize=letter,
                              leftMargin=0.75 * inch, rightMargin=0.75 * inch,
                              topMargin=0.75 * inch, bottomMargin=0.75 * inch)
    styles = getSampleStyleSheet()
    body = ParagraphStyle("body", parent=styles["Normal"],
                            fontName="Times-Roman", fontSize=10.5, leading=13,
                            spaceAfter=8)
    paras = []
    for para in text.split("\n\n"):
        if para.strip():
            paras.append(Paragraph(para.strip().replace("\n", "<br/>"), body))
            paras.append(Spacer(1, 2))
    doc.build(paras)


# ───────────────────────────────────────────────────────────────────────────
# Main
# ───────────────────────────────────────────────────────────────────────────

async def autopilot(max_jobs: int, sort: str, employment_type: str,
                       external_mode: str = "skip"):
    if not OPENAI_API_KEY:
        log("✗ OPENAI_API_KEY not set — aborting")
        return
    ensure_dirs()
    init_db()
    profile = load_user_profile()
    if not profile.get("email"):
        log("✗ Profile incomplete (missing email) — fill via dashboard first")
        return
    log(f"═══ Handshake autopilot @ {datetime.now()}")
    log(f"  emp={employment_type}, sort={sort}, max={max_jobs}, ext={external_mode}")

    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(
            user_data_dir=str(BROWSER_PROFILE), headless=False,
            viewport={"width": 1400, "height": 900})
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        try:
            candidates = await scrape_handshake(page, employment_type, sort)
            log(f"  → {len(candidates)} candidates discovered")
            processed = 0
            submitted = 0
            for c in candidates:
                if processed >= max_jobs:
                    break
                processed += 1
                log(f"\n[{processed}] {c['company']} | {c['title']}")
                try:
                    r = await process_one(page, c, profile, employment_type,
                                              external_mode=external_mode)
                except Exception as e:
                    log(f"  ✗ error: {type(e).__name__}: {e}")
                    continue
                if r.get("action") == "submitted":
                    submitted += 1
                    log(f"  ✓ SUBMITTED ({r.get('coverage')}%)")
                elif r.get("action") == "skip":
                    log(f"  ⏭ {r.get('reason')}")
                else:
                    log(f"  ✗ {r.get('reason', '?')}")
            log(f"\n═══ done. processed={processed}, submitted={submitted}")
        finally:
            try:
                await ctx.close()
            except Exception:
                pass


def main():
    parser = argparse.ArgumentParser(prog="apply_copilot.platforms.handshake")
    parser.add_argument("--max", type=int, default=500)
    parser.add_argument("--sort", choices=["most_relevant", "newest", "soonest_deadline"],
                          default="newest")
    parser.add_argument("--employment-type", choices=["intern", "fulltime"],
                          default="intern")
    parser.add_argument("--external-mode", choices=["skip", "fill", "fill-submit"],
                          default="skip")
    args = parser.parse_args()
    asyncio.run(autopilot(args.max, args.sort, args.employment_type, args.external_mode))


if __name__ == "__main__":
    main()
