"""Integration: applications listing + filter + bundle-state upsert."""
from __future__ import annotations
from datetime import datetime
from apply_copilot.storage import get_session, Submission


def _insert(bundle_slug, **kw):
    """Helper to seed a Submission row."""
    with get_session() as s:
        s.add(Submission(bundle_slug=bundle_slug, **{**{
            "company": kw.get("company", "X"),
            "title": kw.get("title", "Intern"),
            "url": kw.get("url", "https://example.com"),
            "platform": kw.get("platform", "handshake"),
            "employment_type": kw.get("employment_type", "intern"),
            "direction": kw.get("direction", "mle"),
            "resume_filename": kw.get("resume_filename", "mle.docx"),
            "status": kw.get("status", "submitted"),
            "coverage_pct": kw.get("coverage_pct", 80),
        }}))


def test_empty_list(client):
    r = client.get("/api/applications").json()
    assert r["items"] == []
    assert r["total"] == 0


def test_list_returns_inserted(client):
    _insert("acme__intern", company="Acme", title="SDE Intern")
    r = client.get("/api/applications").json()
    assert r["total"] == 1
    assert r["items"][0]["company"] == "Acme"


def test_filter_by_employment_type(client):
    _insert("a__intern", employment_type="intern")
    _insert("b__ft", employment_type="fulltime")
    r = client.get("/api/applications?employment_type=intern").json()
    assert r["total"] == 1
    assert r["items"][0]["employment_type"] == "intern"


def test_filter_by_status(client):
    _insert("a__sub", status="submitted")
    _insert("b__gf", status="gate_fail")
    r = client.get("/api/applications?status=gate_fail").json()
    assert r["total"] == 1
    assert r["items"][0]["status"] == "gate_fail"


def test_bundle_state_upsert(client):
    _insert("foo__bar")
    r = client.post("/api/applications/foo__bar/state",
                     json={"checked": True, "notes": "verified"})
    assert r.status_code == 200

    items = client.get("/api/applications").json()["items"]
    row = next(x for x in items if x["bundle"] == "foo__bar")
    assert row["manual_checked"] is True
    assert row["notes"] == "verified"

    # Update again
    client.post("/api/applications/foo__bar/state", json={"notes": "updated"})
    items = client.get("/api/applications").json()["items"]
    row = next(x for x in items if x["bundle"] == "foo__bar")
    assert row["notes"] == "updated"
    assert row["manual_checked"] is True  # preserved
