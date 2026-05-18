"""Resume Editor endpoints — preview parsed content, translate (en↔zh),
apply manual edits (skills_add / bullet_inject), render to PDF, download.

All operations work on the user's uploaded base resumes (table `Resume`).
Outputs are written to RESUMES_DIR with a _<action>_<timestamp>.docx suffix
and registered as new Resume rows so the user can keep both versions.
"""
from __future__ import annotations
import copy
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from ...config import RESUMES_DIR, GENERATED_DIR, MAX_RESUME_PAGES, ensure_dirs
from ...storage import get_session, Resume
from ...core import resume_editor, translator

router = APIRouter()


# ─── Pydantic payloads ─────────────────────────────────────────────────────

class TranslatePayload(BaseModel):
    target_lang: str   # "zh" or "en"
    source_lang: Optional[str] = None  # auto-detect if None
    save_as_label: Optional[str] = None


class EditOp(BaseModel):
    type: str          # "skills_add" or "bullet_inject"
    category: Optional[str] = None
    keywords: Optional[list[str]] = None
    anchor: Optional[str] = None
    addition: Optional[str] = None


class EditPayload(BaseModel):
    edits: list[EditOp]
    save_as_label: Optional[str] = None
    enforce_page_limit: bool = True


# ─── helpers ───────────────────────────────────────────────────────────────

def _resume_path(resume_id: int) -> tuple[Resume, Path]:
    with get_session() as s:
        r = s.get(Resume, resume_id)
        if not r:
            raise HTTPException(404, "resume not found")
        p = RESUMES_DIR / r.filename
        if not p.exists():
            raise HTTPException(404, "file missing on disk")
        return r, p


def _save_new_resume(doc, source_resume: Resume, suffix: str, label: str) -> dict:
    """Save the modified doc as a new Resume row + .docx file."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    new_filename = f"{source_resume.direction}__{ts}_{suffix}.docx"
    out_path = RESUMES_DIR / new_filename
    resume_editor.save_docx(doc, out_path)
    with get_session() as s:
        r = Resume(direction=source_resume.direction,
                   label=label,
                   filename=new_filename,
                   is_default=False)
        s.add(r)
        s.flush()
        return {"id": r.id, "filename": new_filename, "label": label}


# ─── endpoints ─────────────────────────────────────────────────────────────

@router.get("/{resume_id}/preview")
def preview(resume_id: int):
    """Return parsed paragraphs (text + style summary) for in-browser display."""
    _, p = _resume_path(resume_id)
    doc = resume_editor.load_docx(p)
    paragraphs = []
    for para in doc.paragraphs:
        text = para.text
        if not text.strip():
            continue
        style = (para.style.name if para.style else "Normal")
        any_bold = any((r.bold or False) for r in para.runs)
        paragraphs.append({"text": text, "style": style, "bold": any_bold,
                            "is_bullet": resume_editor._is_bullet_paragraph(para)})
    return {"paragraphs": paragraphs, "language": translator.detect_lang(
        "\n".join(p["text"] for p in paragraphs))}


@router.post("/{resume_id}/translate")
def translate(resume_id: int, payload: TranslatePayload):
    """Translate the resume to `target_lang` (en or zh).

    Saves a NEW Resume row — the original stays. Returns the new row id."""
    if payload.target_lang not in ("zh", "en"):
        raise HTTPException(400, "target_lang must be 'zh' or 'en'")
    src_resume, src_path = _resume_path(resume_id)
    doc = resume_editor.load_docx(src_path)
    result = translator.translate_docx(doc, payload.target_lang, payload.source_lang)
    if result["translated"] == 0:
        # Either same language or LLM unavailable — don't save a useless dup
        raise HTTPException(400, f"no paragraphs translated: {result}")
    label = payload.save_as_label or f"{src_resume.label or src_resume.direction} ({payload.target_lang.upper()})"
    saved = _save_new_resume(doc, src_resume, f"{payload.target_lang}", label)
    return {"ok": True, **saved, "summary": result}


@router.post("/{resume_id}/edit")
def edit(resume_id: int, payload: EditPayload):
    """Apply manual edit ops (skills_add / bullet_inject) with optional page-limit
    rollback. Returns which edits were applied vs reverted."""
    src_resume, src_path = _resume_path(resume_id)
    doc = resume_editor.load_docx(src_path)
    out_pdf = GENERATED_DIR / f"editor_{resume_id}_{datetime.now():%Y%m%d_%H%M%S}.pdf"
    edits_dicts = [e.model_dump(exclude_none=True) for e in payload.edits]
    if payload.enforce_page_limit:
        result = resume_editor.apply_edits_with_rollback(
            doc, edits_dicts, out_pdf, max_pages=MAX_RESUME_PAGES)
    else:
        # Skip rollback machinery — apply all edits and ignore page count
        applied, skipped = [], []
        for e in edits_dicts:
            ok = False
            try:
                if e["type"] == "skills_add":
                    ok = resume_editor.skills_add(doc, e.get("category", ""),
                                                    e.get("keywords") or [])
                elif e["type"] == "bullet_inject":
                    ok = resume_editor.bullet_inject(doc, e.get("anchor", ""),
                                                       e.get("addition", ""))
            except Exception as exc:
                skipped.append({**e, "reason": f"error: {exc}"})
                continue
            (applied if ok else skipped).append(e if ok else {**e, "reason": "anchor not found"})
        result = {"applied": applied, "skipped": skipped, "final_pages": None}

    label = payload.save_as_label or f"{src_resume.label or src_resume.direction} (edited)"
    saved = _save_new_resume(doc, src_resume, "edited", label)
    return {"ok": True, **saved, "edits": result}


@router.get("/{resume_id}/render")
def render(resume_id: int):
    """Render the docx to PDF on-demand. Returns the PDF file as a download."""
    src_resume, src_path = _resume_path(resume_id)
    ensure_dirs()
    pdf_path = GENERATED_DIR / f"{src_resume.filename}.pdf"
    try:
        resume_editor.docx_to_pdf(src_path, pdf_path)
    except RuntimeError as e:
        raise HTTPException(500, f"PDF render failed: {e}")
    return FileResponse(str(pdf_path), filename=pdf_path.name,
                          media_type="application/pdf")
