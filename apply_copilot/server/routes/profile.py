"""Profile CRUD. Single user; row id=1."""
from __future__ import annotations
from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from ...storage import get_session, Profile

router = APIRouter()

PROFILE_FIELDS = [
    "first_name", "last_name", "preferred_name", "pronouns",
    "email", "phone", "phone_country_code", "birth_date",
    "address1", "address2", "city", "state", "postal_code", "country",
    "linkedin", "github", "portfolio",
    "school", "school_degree", "school_major", "school_gpa",
    "school_start_date", "school_end_date", "graduation_date",
    "work_auth_us", "need_sponsorship", "willing_to_relocate",
    "salary_expectation", "available_start_date",
    "gender", "race", "ethnicity", "veteran", "disability", "lgbtq",
    "years_of_experience", "summary",
]
JSON_FIELDS = ["experience", "education", "skills", "project_kb"]


@router.get("")
def get_profile():
    with get_session() as s:
        p = s.get(Profile, 1)
        if not p:
            return {f: ("" if f != "country" else "United States") for f in PROFILE_FIELDS} \
                   | {f: ([] if f != "project_kb" else {}) for f in JSON_FIELDS}
        return _to_dict(p)


@router.put("")
def update_profile(payload: dict):
    with get_session() as s:
        p = s.get(Profile, 1)
        if not p:
            p = Profile(id=1)
            s.add(p)
        for f in PROFILE_FIELDS:
            if f in payload:
                setattr(p, f, payload[f] or "")
        for f in JSON_FIELDS:
            if f in payload:
                setattr(p, f, payload[f])
        return _to_dict(p)


def _to_dict(p: Profile) -> dict:
    d = {f: getattr(p, f) for f in PROFILE_FIELDS}
    for f in JSON_FIELDS:
        d[f] = getattr(p, f) or ([] if f != "project_kb" else {})
    return d
