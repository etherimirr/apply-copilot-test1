"""Upload base resumes (.docx) by direction. Multiple per user."""
from __future__ import annotations
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse

from ...config import RESUMES_DIR, RESUME_DIRECTIONS, ensure_dirs
from ...storage import get_session, Resume

router = APIRouter()


@router.get("")
def list_resumes():
    """List uploaded resumes."""
    ensure_dirs()
    with get_session() as s:
        rs = s.query(Resume).order_by(Resume.uploaded_at.desc()).all()
        return [{
            "id": r.id, "direction": r.direction, "label": r.label,
            "filename": r.filename, "is_default": r.is_default,
            "uploaded_at": r.uploaded_at.isoformat() if r.uploaded_at else "",
        } for r in rs]


@router.post("")
async def upload_resume(
    direction: str = Form(...),
    label: str = Form(""),
    is_default: bool = Form(False),
    file: UploadFile = File(...),
):
    """Save uploaded .docx to RESUMES_DIR and create a Resume row."""
    if direction not in RESUME_DIRECTIONS:
        raise HTTPException(400, f"direction must be one of {RESUME_DIRECTIONS}")
    if not file.filename.lower().endswith(".docx"):
        raise HTTPException(400, "Only .docx is supported. Convert your resume first.")
    ensure_dirs()
    safe_name = f"{direction}__{file.filename}"
    out = RESUMES_DIR / safe_name
    content = await file.read()
    out.write_bytes(content)
    with get_session() as s:
        # If marked default, unset others' default
        if is_default:
            for r in s.query(Resume).filter(Resume.is_default.is_(True)).all():
                r.is_default = False
        r = Resume(direction=direction, label=label or direction,
                   filename=safe_name, is_default=is_default)
        s.add(r)
        s.flush()
        rid = r.id
    return {"id": rid, "filename": safe_name}


@router.delete("/{resume_id}")
def delete_resume(resume_id: int):
    with get_session() as s:
        r = s.get(Resume, resume_id)
        if not r:
            raise HTTPException(404, "not found")
        try:
            (RESUMES_DIR / r.filename).unlink(missing_ok=True)
        except Exception:
            pass
        s.delete(r)
    return {"ok": True}


@router.get("/{resume_id}/download")
def download_resume(resume_id: int):
    with get_session() as s:
        r = s.get(Resume, resume_id)
        if not r:
            raise HTTPException(404, "not found")
        p = RESUMES_DIR / r.filename
        if not p.exists():
            raise HTTPException(404, "file missing")
        return FileResponse(str(p), filename=r.filename)
