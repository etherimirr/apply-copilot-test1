"""Submission history + per-bundle state. Reads from the SQLite Submission table."""
from __future__ import annotations
from fastapi import APIRouter
from sqlalchemy import select

from ...storage import get_session, Submission, BundleState

router = APIRouter()


@router.get("")
def list_applications(employment_type: str = "", status: str = ""):
    """List submissions, optionally filtered by employment_type / status."""
    with get_session() as s:
        q = select(Submission).order_by(Submission.submitted_at.desc())
        rows = s.execute(q).scalars().all()
        states = {b.bundle_slug: b for b in s.query(BundleState).all()}

    items = []
    for r in rows:
        if employment_type and r.employment_type != employment_type:
            continue
        if status and r.status != status:
            continue
        st = states.get(r.bundle_slug)
        items.append({
            "id": r.id, "bundle": r.bundle_slug,
            "company": r.company, "title": r.title, "url": r.url,
            "platform": r.platform, "employment_type": r.employment_type,
            "direction": r.direction, "resume_filename": r.resume_filename,
            "status": r.status, "coverage_pct": r.coverage_pct,
            "submitted_at": r.submitted_at.isoformat() if r.submitted_at else "",
            "withdrawn_at": r.withdrawn_at.isoformat() if r.withdrawn_at else "",
            "manual_checked": bool(st.checked) if st else False,
            "notes": st.notes if st else "",
        })
    return {"items": items, "total": len(items)}


@router.post("/{bundle_slug}/state")
def update_state(bundle_slug: str, payload: dict):
    with get_session() as s:
        st = s.get(BundleState, bundle_slug)
        if not st:
            st = BundleState(bundle_slug=bundle_slug)
            s.add(st)
        if "checked" in payload:
            st.checked = bool(payload["checked"])
        if "notes" in payload:
            st.notes = payload["notes"] or ""
    return {"ok": True}
