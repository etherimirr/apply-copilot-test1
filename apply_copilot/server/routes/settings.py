"""Settings: gate threshold, max pages, etc. — exposed via env-vars OR DB."""
from __future__ import annotations
from fastapi import APIRouter

from ...config import (
    AUTO_SUBMIT_MIN_COVERAGE, MAX_RESUME_PAGES,
    OPENAI_API_KEY, OPENAI_MODEL_CHEAP, OPENAI_MODEL_STRONG,
    DATA_ROOT,
)

router = APIRouter()


@router.get("")
def get_settings():
    """Returns current settings + diagnostics. Mostly read-only at this point;
    user changes things via env vars."""
    return {
        "data_root": str(DATA_ROOT),
        "openai_key_set": bool(OPENAI_API_KEY),
        "models": {"cheap": OPENAI_MODEL_CHEAP, "strong": OPENAI_MODEL_STRONG},
        "gate_pct": AUTO_SUBMIT_MIN_COVERAGE,
        "max_pages": MAX_RESUME_PAGES,
    }
