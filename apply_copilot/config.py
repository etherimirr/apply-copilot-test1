"""Centralized, cross-platform configuration.

All paths derive from $APPLY_COPILOT_HOME (default: ~/.apply_copilot).
Works on macOS, Linux, Windows — no /opt/homebrew, no /Users/, all pathlib.
"""
from __future__ import annotations
import os
import platform
import subprocess
from pathlib import Path


# Data root (per-user, override with $APPLY_COPILOT_HOME)
DATA_ROOT = Path(os.environ.get("APPLY_COPILOT_HOME", str(Path.home() / ".apply_copilot")))

# Per-user data
PROFILE_JSON = DATA_ROOT / "profile.json"           # personal info (filled via dashboard)
QA_MEMORY_JSON = DATA_ROOT / "qa_memory.json"       # accumulated Q&A answers
SUBMISSIONS_DB = DATA_ROOT / "submissions.sqlite"   # SQLite for history
RESUMES_DIR = DATA_ROOT / "resumes"                 # user-uploaded base resumes (.docx)
GENERATED_DIR = DATA_ROOT / "generated"             # per-job rendered PDFs
BROWSER_PROFILE = DATA_ROOT / "browser"             # Playwright Chrome for Testing profile
LOGS_DIR = DATA_ROOT / "logs"
SCREENSHOTS_DIR = DATA_ROOT / "screenshots"

# Server
SERVER_HOST = os.environ.get("APPLY_COPILOT_HOST", "127.0.0.1")
SERVER_PORT = int(os.environ.get("APPLY_COPILOT_PORT", "8787"))

# OpenAI
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_MODEL_CHEAP = os.environ.get("APPLY_COPILOT_LLM_MINI", "gpt-4o-mini")
OPENAI_MODEL_STRONG = os.environ.get("APPLY_COPILOT_LLM_STRONG", "gpt-4o")

# Limits / behavior
AUTO_SUBMIT_MIN_COVERAGE = int(os.environ.get("APPLY_COPILOT_GATE_PCT", "55"))
MAX_RESUME_PAGES = int(os.environ.get("APPLY_COPILOT_MAX_PAGES", "2"))

# Resume directions — keys correspond to user-uploaded resume slots
RESUME_DIRECTIONS = ["agent", "mle", "sde_general", "sde_dl", "default"]


def ensure_dirs():
    """Create all data dirs on first run."""
    for d in (DATA_ROOT, RESUMES_DIR, GENERATED_DIR, BROWSER_PROFILE, LOGS_DIR, SCREENSHOTS_DIR):
        d.mkdir(parents=True, exist_ok=True)


# ─── Cross-platform helpers ────────────────────────────────────────────────

def open_path_in_file_manager(p: Path):
    """Open a file or folder in the user's default file manager.
    Replaces macOS `open <path>`.
    """
    p = Path(p)
    if not p.exists():
        return
    sys = platform.system()
    try:
        if sys == "Darwin":
            subprocess.run(["open", str(p)], check=False)
        elif sys == "Windows":
            os.startfile(str(p))  # type: ignore[attr-defined]
        elif sys == "Linux":
            subprocess.run(["xdg-open", str(p)], check=False)
    except Exception:
        pass


def pdf_to_text(pdf_path: Path) -> str:
    """Extract plain text from a PDF using pdfminer (no system pdftotext bin).
    Replaces the macOS `/opt/homebrew/bin/pdftotext` hardcoded path.
    """
    from pdfminer.high_level import extract_text
    try:
        return extract_text(str(pdf_path)) or ""
    except Exception:
        return ""


def pdf_page_count(pdf_path: Path) -> int:
    """Page count via pypdf — cross-platform, no shell."""
    from pypdf import PdfReader
    try:
        return len(PdfReader(str(pdf_path)).pages)
    except Exception:
        return 0
