"""Unit: SQLite init, Profile / Resume / Submission CRUD."""
from __future__ import annotations
from datetime import datetime

from apply_copilot.storage import init_db, get_session, Profile, Resume, Submission, BundleState


def test_init_db_creates_tables():
    """init_db is idempotent and creates all tables."""
    init_db()
    init_db()  # call twice; must not error
    with get_session() as s:
        # Smoke: each query must succeed (no missing table)
        s.query(Profile).count()
        s.query(Resume).count()
        s.query(Submission).count()
        s.query(BundleState).count()


def test_profile_insert_and_update():
    """Profile is a single row id=1; subsequent updates mutate in place."""
    init_db()
    with get_session() as s:
        p = Profile(id=1, first_name="Alice", last_name="Tester",
                    email="a@example.com", country="United States")
        s.add(p)
    with get_session() as s:
        p = s.get(Profile, 1)
        assert p.first_name == "Alice"
        assert p.email == "a@example.com"
        p.first_name = "Alicia"
    with get_session() as s:
        assert s.get(Profile, 1).first_name == "Alicia"


def test_resume_unique_default_handled_in_route():
    """Multiple resumes can exist; only one should be is_default at a time
    (the route enforces; the model permits multiple — see route logic)."""
    init_db()
    with get_session() as s:
        s.add(Resume(direction="mle", label="ml-v1", filename="mle__r.docx", is_default=True))
        s.add(Resume(direction="sde_general", label="sde-v1", filename="sde__r.docx",
                     is_default=False))
    with get_session() as s:
        assert s.query(Resume).count() == 2
        defaults = s.query(Resume).filter(Resume.is_default.is_(True)).count()
        assert defaults == 1  # only first one inserted has it set True


def test_submission_round_trip():
    """Insert + read submission; statuses round-trip."""
    init_db()
    with get_session() as s:
        s.add(Submission(
            bundle_slug="foo_co__sde_intern",
            company="Foo Co", title="SDE Intern",
            url="https://example.com/job/1",
            platform="handshake", employment_type="intern",
            direction="sde_general", resume_filename="sde_general__r.docx",
            status="submitted", coverage_pct=85,
        ))
    with get_session() as s:
        row = s.query(Submission).filter_by(bundle_slug="foo_co__sde_intern").first()
        assert row.company == "Foo Co"
        assert row.coverage_pct == 85
        assert row.status == "submitted"


def test_bundle_state_upsert_pattern():
    """BundleState uses bundle_slug as PK; route does its own upsert."""
    init_db()
    with get_session() as s:
        s.add(BundleState(bundle_slug="x", checked=True, notes="hi"))
    with get_session() as s:
        st = s.get(BundleState, "x")
        assert st.checked is True
        assert st.notes == "hi"
