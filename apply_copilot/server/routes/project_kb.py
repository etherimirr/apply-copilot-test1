"""Project KB CRUD — per-project markdown blobs used to ground LLM answers.

Stored as a JSON dict on Profile.project_kb (project_id -> markdown text).
The dashboard provides a simple textarea + slug per project.
"""
from __future__ import annotations
from fastapi import APIRouter, HTTPException

from ...storage import get_session, Profile

router = APIRouter()


def _ensure_profile(s) -> Profile:
    p = s.get(Profile, 1)
    if not p:
        p = Profile(id=1)
        s.add(p)
        s.flush()
    if not isinstance(p.project_kb, dict):
        p.project_kb = {}
    return p


@router.get("")
def list_projects():
    with get_session() as s:
        p = _ensure_profile(s)
        kb = p.project_kb or {}
        items = [{"id": k, "preview": (v or "")[:120], "chars": len(v or "")}
                  for k, v in sorted(kb.items())]
    return {"items": items, "total": len(items)}


@router.get("/{project_id}")
def get_project(project_id: str):
    with get_session() as s:
        p = _ensure_profile(s)
        kb = p.project_kb or {}
        if project_id not in kb:
            raise HTTPException(404, detail="not found")
        return {"id": project_id, "content": kb[project_id]}


@router.put("/{project_id}")
def upsert_project(project_id: str, payload: dict):
    content = (payload.get("content") or "").strip()
    if not content:
        raise HTTPException(400, detail="content required")
    pid = project_id.strip().lower().replace(" ", "_")
    if not pid:
        raise HTTPException(400, detail="invalid project_id")
    with get_session() as s:
        p = _ensure_profile(s)
        kb = dict(p.project_kb or {})
        kb[pid] = content
        p.project_kb = kb
    return {"ok": True, "id": pid, "chars": len(content)}


@router.delete("/{project_id}")
def delete_project(project_id: str):
    with get_session() as s:
        p = _ensure_profile(s)
        kb = dict(p.project_kb or {})
        if project_id not in kb:
            raise HTTPException(404, detail="not found")
        del kb[project_id]
        p.project_kb = kb
    return {"ok": True}
