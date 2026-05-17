"""Generic external-apply form filler. Walks the DOM, classifies each field by
label/name/placeholder, fills known values from the user's profile, generates
answers for open-ended questions via LLM, and uploads files.

STOPS BEFORE clicking Submit unless the caller explicitly opts in. The
autopilot never opts in — it fills, then leaves the tab open / closes / skips
depending on external-mode policy.

Handles Greenhouse / Lever / Ashby / Workable / generic forms via label
heuristics. Workday has its own multi-step handler (workday.py).
"""
from __future__ import annotations
import sys
from pathlib import Path
from typing import Optional

from playwright.async_api import Page, TimeoutError as PWTimeoutError

import re

from .detect import detect_ats
from .field_classify import classify_field, value_for, is_demographic
from ...core.llm_answer import answer_question, yes_no_for
from ...core.grounded_blurb import write_grounded_blurb, pick_project_for_question


_PROJECT_BLURB_PATTERNS = [
    r"\ba project\b", r"\bdescribe a project\b", r"\bproject you'?ve built\b",
    r"\btell us about a project\b", r"\bmost ambitious project\b",
    r"\bshow us something\b", r"\bwriting sample\b",
    r"\ba (claude code|agent|fine[\s-]tuning|ml|sde) project\b",
]


def _looks_like_project_question(text: str) -> bool:
    low = (text or "").lower()
    return any(re.search(p, low) for p in _PROJECT_BLURB_PATTERNS)


# ─── DOM walker ─────────────────────────────────────────────────────────────

# Returns every visible, non-hidden, non-disabled input/textarea/select on the
# page along with its best-effort label, and groups radios by `name`.
SCAN_JS = r"""
() => {
    function labelFor(el) {
        if (el.id) {
            const lab = document.querySelector(`label[for="${el.id}"]`);
            if (lab) return (lab.innerText || '').trim();
        }
        let p = el.parentElement;
        for (let i = 0; i < 4 && p; i++) {
            if (p.tagName === 'LABEL') return (p.innerText || '').trim();
            p = p.parentElement;
        }
        if (el.getAttribute('aria-label')) return el.getAttribute('aria-label');
        const labelledBy = el.getAttribute('aria-labelledby');
        if (labelledBy) {
            const labEl = document.getElementById(labelledBy);
            if (labEl) return (labEl.innerText || '').trim();
        }
        let prev = el.previousElementSibling;
        for (let i = 0; i < 3 && prev; i++) {
            const t = (prev.innerText || '').trim();
            if (t && t.length < 150) return t;
            prev = prev.previousElementSibling;
        }
        return '';
    }
    function isVisible(el) {
        const r = el.getBoundingClientRect();
        if (r.width === 0 || r.height === 0) return false;
        const cs = window.getComputedStyle(el);
        if (cs.display === 'none' || cs.visibility === 'hidden' || cs.opacity === '0') return false;
        return true;
    }

    const fields = [];
    const els = document.querySelectorAll(
        'input:not([type="hidden"]):not([type="submit"]):not([type="button"]),' +
        'textarea, select'
    );
    for (const el of els) {
        if (!isVisible(el)) continue;
        if (el.disabled || el.readOnly) continue;
        const t = (el.type || '').toLowerCase();
        if (t === 'radio') continue;  // handled below as groups
        const label = labelFor(el);
        fields.push({
            tag: el.tagName.toLowerCase(),
            type: t,
            name: el.name || '',
            id: el.id || '',
            placeholder: el.placeholder || '',
            ariaLabel: el.getAttribute('aria-label') || '',
            required: !!el.required,
            value: (el.value || '').trim(),
            label: label,
            options: el.tagName.toLowerCase() === 'select'
                ? Array.from(el.options).map(o => ({value: o.value, text: o.text})) : []
        });
    }
    // Group radios by name
    const radios = document.querySelectorAll('input[type="radio"]');
    const groups = {};
    for (const r of radios) {
        if (!isVisible(r)) continue;
        if (!r.name) continue;
        if (!groups[r.name]) {
            groups[r.name] = {
                tag: 'radio', type: 'radio', name: r.name, id: r.id || '',
                placeholder: '', ariaLabel: '', required: !!r.required,
                value: '', label: '', options: [],
            };
            let p = r.parentElement;
            for (let i = 0; i < 5 && p; i++) {
                if (p.tagName === 'FIELDSET') {
                    const lg = p.querySelector('legend');
                    if (lg) { groups[r.name].label = (lg.innerText || '').trim(); break; }
                }
                p = p.parentElement;
            }
        }
        groups[r.name].options.push({value: r.value, text: labelFor(r) || r.value});
    }
    for (const g of Object.values(groups)) fields.push(g);
    return fields;
}
"""


async def scan_fields(page: Page) -> list[dict]:
    try:
        return await page.evaluate(SCAN_JS)
    except Exception as e:
        print(f"  [filler] scan failed: {e}", file=sys.stderr)
        return []


# ─── Fill primitives ────────────────────────────────────────────────────────

def _selector_for(field: dict) -> Optional[str]:
    if field.get("id"):
        return f'#{field["id"]}'
    if field.get("name"):
        name = field["name"].replace('"', '\\"')
        return f'{field["tag"]}[name="{name}"]'
    return None


async def fill_text(page: Page, field: dict, value: str) -> bool:
    if not value:
        return False
    sel = _selector_for(field)
    if not sel:
        return False
    try:
        await page.locator(sel).first.fill(value, timeout=3000)
        return True
    except Exception as e:
        print(f"    [filler] fill {sel} failed: {e}", file=sys.stderr)
        return False


async def fill_select(page: Page, field: dict, value: str) -> bool:
    if not value:
        return False
    sel = _selector_for(field)
    if not sel:
        return False
    options = field.get("options") or []
    target = value.strip().lower()
    chosen = None
    for o in options:
        if (o.get("value") or "").lower() == target:
            chosen = o["value"]; break
    if not chosen:
        for o in options:
            if (o.get("text") or "").lower() == target:
                chosen = o["value"]; break
    if not chosen:
        for o in options:
            if target and target in (o.get("text") or "").lower():
                chosen = o["value"]; break
    if not chosen:
        return False
    try:
        await page.locator(sel).first.select_option(value=chosen, timeout=3000)
        return True
    except Exception as e:
        print(f"    [filler] select {sel} failed: {e}", file=sys.stderr)
        return False


async def click_radio(page: Page, field: dict, value: str) -> bool:
    if not value or not field.get("options"):
        return False
    target = value.strip().lower()
    chosen = None
    for o in field["options"]:
        if (o.get("value") or "").lower() == target or \
           (o.get("text") or "").lower() == target:
            chosen = o["value"]; break
    if not chosen:
        for o in field["options"]:
            if target in (o.get("text") or "").lower():
                chosen = o["value"]; break
    if not chosen:
        return False
    name = field["name"].replace('"', '\\"')
    val = chosen.replace('"', '\\"')
    sel = f'input[type="radio"][name="{name}"][value="{val}"]'
    try:
        await page.locator(sel).first.check(timeout=3000)
        return True
    except Exception as e:
        print(f"    [filler] radio {sel} failed: {e}", file=sys.stderr)
        return False


async def upload_file(page: Page, field: dict, path: Path) -> bool:
    if not path or not path.exists():
        return False
    sel = _selector_for(field)
    if not sel:
        return False
    try:
        await page.locator(sel).first.set_input_files(str(path), timeout=15000)
        return True
    except Exception as e:
        print(f"    [filler] upload {sel} failed: {e}", file=sys.stderr)
        return False


# ─── Submit-button probe ────────────────────────────────────────────────────

SUBMIT_SELECTORS = [
    'button:has-text("Submit Application")',
    'button:has-text("Submit application")',
    'button:has-text("Submit")',
    'button[type="submit"]',
    'input[type="submit"]',
]


async def find_submit_button(page: Page) -> bool:
    for sel in SUBMIT_SELECTORS:
        try:
            if await page.locator(sel).first.count() > 0:
                return True
        except Exception:
            pass
    return False


# ─── Main orchestrator ──────────────────────────────────────────────────────

async def fill_application(
    page: Page,
    profile: dict,
    *,
    direction: str = "",
    jd: str = "",
    company: str = "",
    title: str = "",
    resume_path: Optional[Path] = None,
    cover_letter_path: Optional[Path] = None,
    transcript_path: Optional[Path] = None,
    submit: bool = False,
    use_llm_for_open_questions: bool = True,
    skip_demographics: bool = True,
) -> dict:
    """Fill one external-apply page. Returns a structured report.

    The caller passes the profile dict (loaded from SQLite) and optional
    file paths. Nothing is hardcoded to a specific user.
    """
    ats = detect_ats(page.url)
    print(f"  [filler] ATS={ats}, url={page.url[:100]}")

    try:
        await page.wait_for_selector("input, textarea, select", timeout=15000)
    except PWTimeoutError:
        return {"ok": False, "reason": "no form found after 15s", "ats": ats}
    await page.wait_for_timeout(1500)

    result: dict = {
        "ok": True, "ats": ats, "url": page.url,
        "filled": [], "skipped": [], "open_questions": [], "unclassified": [],
    }

    fields = await scan_fields(page)
    print(f"  [filler] scanned {len(fields)} visible fields")

    for f in fields:
        label = f.get("label") or ""
        name = f.get("name") or ""
        placeholder = f.get("placeholder") or ""
        aria = f.get("ariaLabel") or ""
        ftype = f.get("type") or ""
        tag = f.get("tag") or ""
        ident = (label[:50] or name or placeholder)[:60]

        # User pre-filled (e.g. autofill / resumed mid-fill) — leave it alone
        if f.get("value") and tag != "select":
            result["skipped"].append(f"{ident} (pre-filled)")
            continue

        # File uploads
        if ftype == "file":
            cls = classify_field(label, name, placeholder, aria, input_type="file")
            kind = cls[0] if cls else "resume"
            path_map = {
                "resume": resume_path,
                "cover_letter": cover_letter_path,
                "transcript": transcript_path,
            }
            path = path_map.get(kind)
            if path and path.exists():
                if await upload_file(page, f, path):
                    result["filled"].append(f"file:{kind} -> {ident}")
                    continue
            result["skipped"].append(f"file:{kind} (no path or upload failed): {ident}")
            continue

        # Classify by label
        cls = classify_field(label, name, placeholder, aria, ftype)
        if cls:
            canonical, key = cls
            if skip_demographics and is_demographic(canonical):
                result["skipped"].append(f"{canonical} (demographics skip): {ident}")
                continue
            val = value_for(canonical, profile, key) if key else ""
            # Y/N override
            if canonical in ("work_auth_us", "needs_sponsorship", "willing_to_relocate"):
                yn = yes_no_for(label or name, profile)
                if yn:
                    val = yn
            if not val:
                result["skipped"].append(f"{canonical} (no value in profile): {ident}")
                continue
            ok = False
            if tag == "select":
                ok = await fill_select(page, f, val)
            elif tag == "radio":
                ok = await click_radio(page, f, val)
            elif tag == "textarea" or ftype in ("text", "email", "tel", "url", "number", "search", ""):
                ok = await fill_text(page, f, val)
            if ok:
                result["filled"].append(f"{canonical}={val[:40]!r} -> {ident}")
            else:
                result["skipped"].append(f"{canonical} (fill failed): {ident}")
            continue

        # Unclassified: treat textareas / long-label inputs as open questions
        is_open = (tag == "textarea") or (label and len(label) > 30)
        if is_open and use_llm_for_open_questions:
            q_text = label or placeholder or name
            if not q_text or len(q_text) < 10:
                result["unclassified"].append(ident)
                continue
            yn = yes_no_for(q_text, profile)
            if yn and tag != "textarea":
                if await fill_text(page, f, yn):
                    result["filled"].append(f"yn={yn} -> {ident}")
                    continue
            try:
                # If the question reads like "describe a project you've built",
                # use the grounded-blurb path (single KB entry, structured prompt).
                if (_looks_like_project_question(q_text) and
                        (profile.get("project_kb") or {})):
                    pid = pick_project_for_question(
                        question=q_text, project_kb=profile["project_kb"], jd=jd,
                    )
                    kb = (profile["project_kb"] or {}).get(pid, "")
                    ans = write_grounded_blurb(
                        project_id=pid or "project", project_kb=kb,
                        jd=jd, company=company, title=title,
                        section_instruction=q_text,
                    )
                else:
                    ans = answer_question(q_text, jd=jd, company=company,
                                           title=title, direction=direction,
                                           profile=profile)
            except Exception as e:
                result["skipped"].append(f"open-q LLM error ({e}): {q_text[:50]}")
                continue
            if not ans:
                result["skipped"].append(f"open-q LLM empty: {q_text[:50]}")
                continue
            if await fill_text(page, f, ans):
                result["filled"].append(f"llm-answer -> {ident}")
                result["open_questions"].append({"q": q_text, "a": ans})
            else:
                result["skipped"].append(f"open-q fill failed: {q_text[:50]}")
            continue

        result["unclassified"].append(ident)

    submit_present = await find_submit_button(page)
    result["submit_button_present"] = submit_present
    result["submitted"] = False

    if submit_present and submit:
        # Caller explicitly opted in. Autopilot must NEVER pass submit=True for
        # external ATS pages — that's user-review territory.
        for sel in SUBMIT_SELECTORS:
            try:
                await page.locator(sel).first.click(timeout=4000)
                result["submitted"] = True
                break
            except Exception:
                pass

    return result
