"""Start / stop autopilot runs from the dashboard. Currently a stub —
wires to apply_copilot.platforms.handshake in a worker subprocess.
"""
from __future__ import annotations
import os
import sys
import signal
import subprocess
from pathlib import Path

from fastapi import APIRouter, HTTPException

from ...config import LOGS_DIR, OPENAI_API_KEY

router = APIRouter()

_RUN = {"proc": None, "logfile": None}


@router.get("/status")
def status():
    p = _RUN["proc"]
    if not p:
        return {"running": False}
    return {"running": p.poll() is None, "pid": p.pid,
            "logfile": str(_RUN["logfile"]) if _RUN["logfile"] else ""}


@router.post("/start")
def start(payload: dict):
    """Launch a new autopilot worker.
    Body: {"platform": "handshake", "employment_type": "intern|fulltime|both",
           "sort": "newest|most_relevant|soonest_deadline",
           "max_jobs": 500, "external_mode": "skip|fill|fill-submit"}
    """
    if _RUN["proc"] and _RUN["proc"].poll() is None:
        raise HTTPException(409, "autopilot already running")
    if not OPENAI_API_KEY:
        raise HTTPException(400, "OPENAI_API_KEY not set in environment")
    platform = payload.get("platform", "handshake")
    if platform != "handshake":
        raise HTTPException(400, "only handshake supported for now")
    args = [
        sys.executable, "-u", "-m", "apply_copilot.platforms.handshake",
        "--max", str(payload.get("max_jobs", 500)),
        "--sort", payload.get("sort", "newest"),
        "--employment-type", payload.get("employment_type", "intern"),
        "--external-mode", payload.get("external_mode", "skip"),
    ]
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    from datetime import datetime
    logfile = LOGS_DIR / f"autopilot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    f = open(logfile, "a", buffering=1)
    proc = subprocess.Popen(args, stdout=f, stderr=subprocess.STDOUT,
                            env={**os.environ})
    _RUN["proc"] = proc
    _RUN["logfile"] = logfile
    return {"pid": proc.pid, "logfile": str(logfile)}


@router.post("/stop")
def stop():
    p = _RUN["proc"]
    if not p or p.poll() is not None:
        return {"running": False}
    try:
        p.terminate()
        p.wait(timeout=5)
    except subprocess.TimeoutExpired:
        p.kill()
    return {"stopped": True}


@router.get("/log")
def tail_log(lines: int = 200):
    """Tail of the current log file."""
    if not _RUN["logfile"] or not _RUN["logfile"].exists():
        return {"lines": []}
    text = _RUN["logfile"].read_text(encoding="utf-8", errors="ignore")
    return {"lines": text.splitlines()[-lines:]}
