"""docx-aware resume editor — preserves user's format, enforces ≤ MAX_RESUME_PAGES.

Design principles:
1. **Format preservation**: read user's .docx, edit IN-PLACE via python-docx.
   Don't replace their fonts, paragraph styles, headers, footers, dividers.
2. **Only add, never delete** user's existing content.
3. **Bold only the added** phrases (so the diff is visible to user + recruiter).
4. **≤ MAX_RESUME_PAGES**: after every edit, render to PDF, count pages.
   If over, revert the last edit.

Edit operations:
- skills_add(category, keywords) — append to Skills paragraph
- bullet_inject(anchor_text, keywords) — append to existing bullet matching anchor
- (project_swap is intentionally NOT here — too risky to swap a project the user
  uploaded; we leave that to a separate "rewrite this section" UI in the future)
"""
from __future__ import annotations
import copy
import re
from pathlib import Path
from typing import Optional

from ..config import MAX_RESUME_PAGES, GENERATED_DIR, pdf_page_count


def load_docx(path: Path):
    """Load a docx Document. Raises if not a .docx file."""
    from docx import Document
    return Document(str(path))


def save_docx(doc, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(path))


def docx_to_text(doc) -> str:
    """Concatenate all paragraph text. Used to compute keyword coverage on the
    edited resume without round-tripping to PDF (faster)."""
    return "\n".join(p.text for p in doc.paragraphs if p.text.strip())


def docx_to_pdf(docx_path: Path, pdf_path: Optional[Path] = None) -> Path:
    """Convert .docx → .pdf cross-platform.

    Strategy:
    - macOS / Linux: use LibreOffice if available (most reliable)
    - Fallback: use docx2pdf (Windows preferred)
    - Fallback: skip and return docx path (caller must handle)
    """
    import platform
    import subprocess
    docx_path = Path(docx_path)
    if pdf_path is None:
        pdf_path = docx_path.with_suffix(".pdf")
    pdf_path = Path(pdf_path)
    pdf_path.parent.mkdir(parents=True, exist_ok=True)

    sys = platform.system()

    # Strategy 1: docx2pdf (cross-platform; uses Word on Windows, LibreOffice elsewhere)
    try:
        from docx2pdf import convert
        convert(str(docx_path), str(pdf_path))
        if pdf_path.exists():
            return pdf_path
    except Exception:
        pass

    # Strategy 2: LibreOffice (macOS/Linux)
    for lo in ("soffice", "libreoffice",
                "/Applications/LibreOffice.app/Contents/MacOS/soffice"):
        try:
            r = subprocess.run([lo, "--headless", "--convert-to", "pdf",
                                  "--outdir", str(pdf_path.parent), str(docx_path)],
                                capture_output=True, timeout=60)
            if r.returncode == 0 and pdf_path.exists():
                return pdf_path
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue

    raise RuntimeError(
        "Couldn't convert .docx → .pdf. Install LibreOffice (free) or Microsoft Word, "
        "or `pip install docx2pdf`."
    )


# ───────────────────────────────────────────────────────────────────────────
# Edit operations
# ───────────────────────────────────────────────────────────────────────────

def add_bold_run(paragraph, text: str):
    """Append a new run to a paragraph with bold formatting (visually marks the
    addition). The run inherits the paragraph's font / size by default."""
    run = paragraph.add_run(text)
    run.bold = True
    return run


def _find_skills_paragraph(doc, category_keyword: str):
    """Find a paragraph in the Skills section whose label matches
    category_keyword (e.g. 'Programming Languages', 'ML Frameworks').

    Heuristic: look for paragraphs containing a colon ':' and the keyword.
    """
    target_low = category_keyword.lower()
    candidates = []
    for p in doc.paragraphs:
        t = p.text.strip()
        if ":" not in t:
            continue
        label = t.split(":", 1)[0].lower()
        if target_low in label or label in target_low:
            candidates.append(p)
    return candidates[0] if candidates else None


def skills_add(doc, category: str, new_keywords: list[str]) -> bool:
    """Append new keywords to the matching skills category paragraph.
    Bolds only the new keywords. Returns True if applied."""
    if not new_keywords:
        return False
    p = _find_skills_paragraph(doc, category)
    if p is None:
        return False
    # Append ", <bold kw1>, <bold kw2>, ..."
    # First a separator run (non-bold)
    sep = p.add_run(", ")
    sep.bold = False
    for i, kw in enumerate(new_keywords):
        add_bold_run(p, kw)
        if i < len(new_keywords) - 1:
            comma = p.add_run(", ")
            comma.bold = False
    return True


def _is_bullet_paragraph(p) -> bool:
    """Detect bullet-list paragraphs.
    python-docx's .style.name may say 'Normal' but inline `<w:numPr>` indicates
    a numbered/bulleted list. Check both."""
    name = (p.style.name or "").lower() if p.style else ""
    if "bullet" in name or "list" in name:
        return True
    # Inline w:numPr check
    pPr = p._element.find("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}pPr")
    if pPr is not None:
        numPr = pPr.find("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}numPr")
        if numPr is not None:
            return True
    return False


def bullet_inject(doc, anchor_text: str, addition: str) -> bool:
    """Append <addition> (bolded) to an existing bullet whose text starts with
    anchor_text. Returns True if applied."""
    if not anchor_text or not addition:
        return False
    anchor_low = anchor_text[:30].lower()
    for p in doc.paragraphs:
        if not p.text:
            continue
        if not p.text.lower().startswith(anchor_low):
            continue
        # Found the anchor. Append " (addition)" with the addition bolded.
        if not p.text.rstrip().endswith((".", ",", ";")):
            p.add_run(" ")
        else:
            p.add_run(" ")
        run = p.add_run(addition)
        run.bold = True
        return True
    return False


# ───────────────────────────────────────────────────────────────────────────
# Page count enforcement
# ───────────────────────────────────────────────────────────────────────────

def enforce_page_limit(doc, output_pdf_path: Path,
                       max_pages: Optional[int] = None) -> tuple[Path, int]:
    """Save doc, render PDF, count pages. Returns (pdf_path, page_count).
    Caller decides whether to revert if page_count > max_pages.
    """
    if max_pages is None:
        max_pages = MAX_RESUME_PAGES
    output_pdf_path = Path(output_pdf_path)
    tmp_docx = output_pdf_path.with_suffix(".docx")
    save_docx(doc, tmp_docx)
    try:
        pdf = docx_to_pdf(tmp_docx, output_pdf_path)
    except RuntimeError as e:
        print(f"  [resume_editor] PDF render skipped: {e}")
        return tmp_docx, 0
    pages = pdf_page_count(pdf)
    return pdf, pages


# ───────────────────────────────────────────────────────────────────────────
# Apply a batch of edits with rollback
# ───────────────────────────────────────────────────────────────────────────

def apply_edits_with_rollback(doc, edits: list[dict],
                                  output_pdf: Path,
                                  max_pages: Optional[int] = None) -> dict:
    """Apply edits one by one; after each, re-render + check page count.
    If page count exceeds max, revert that edit (restore doc snapshot)
    and try the next.

    edits is a list of dicts:
      {"type": "skills_add", "category": "...", "keywords": [...]}
      {"type": "bullet_inject", "anchor": "...", "addition": "..."}

    Returns: {"applied": [edits that stuck], "skipped": [edits reverted],
              "final_pages": N, "pdf_path": Path}
    """
    if max_pages is None:
        max_pages = MAX_RESUME_PAGES
    applied, skipped = [], []
    pdf_path = None
    final_pages = 0
    body = doc.element.body
    for e in edits:
        # Snapshot the body's children only — python-docx caches references
        # into doc._body._element, so we mutate IN PLACE on rollback rather
        # than swapping the element out.
        before_children = [copy.deepcopy(c) for c in body]
        ok = False
        try:
            if e["type"] == "skills_add":
                ok = skills_add(doc, e.get("category", ""),
                                 e.get("keywords", []) or [])
            elif e["type"] == "bullet_inject":
                ok = bullet_inject(doc, e.get("anchor", ""),
                                    e.get("addition", ""))
        except Exception as exc:
            ok = False
            skipped.append({**e, "reason": f"edit error: {exc}"})
            continue
        if not ok:
            skipped.append({**e, "reason": "anchor not found"})
            continue
        pdf_path, pages = enforce_page_limit(doc, output_pdf, max_pages)
        final_pages = pages
        if pages > max_pages:
            # Restore body children in place
            for child in list(body):
                body.remove(child)
            for child in before_children:
                body.append(child)
            skipped.append({**e, "reason": f"would exceed {max_pages} pages "
                                              f"(got {pages})"})
            pdf_path, final_pages = enforce_page_limit(doc, output_pdf, max_pages)
            continue
        applied.append(e)
    return {"applied": applied, "skipped": skipped,
            "final_pages": final_pages,
            "pdf_path": pdf_path}
