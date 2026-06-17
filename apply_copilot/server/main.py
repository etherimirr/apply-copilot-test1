"""FastAPI app — serves the SPA dashboard + REST endpoints.

The dashboard has 4 tabs:
  - Profile (edit personal info form)
  - Resumes (upload .docx files per direction)
  - Autopilot (start / stop runs, status)
  - Applications (history with filters)
"""
from __future__ import annotations
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from .routes import profile, resumes, autopilot, applications, settings, project_kb, resume_editor

app = FastAPI(title="Apply Copilot")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

# Mount static
STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# API
app.include_router(profile.router, prefix="/api/profile")
app.include_router(resumes.router, prefix="/api/resumes")
app.include_router(autopilot.router, prefix="/api/autopilot")
app.include_router(applications.router, prefix="/api/applications")
app.include_router(settings.router, prefix="/api/settings")
app.include_router(project_kb.router, prefix="/api/project-kb")
app.include_router(resume_editor.router, prefix="/api/resumes")


@app.get("/")
def root():
    return FileResponse(str(STATIC_DIR / "index.html"))


@app.get("/health")
def health():
    return {"ok": True}
