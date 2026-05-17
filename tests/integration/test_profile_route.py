"""Integration: profile GET / PUT round-trip via TestClient + SQLite."""
from __future__ import annotations


def test_get_returns_empty_profile_initially(client):
    r = client.get("/api/profile")
    assert r.status_code == 200
    d = r.json()
    # Defaults — most fields empty, country defaults to "United States"
    assert d["first_name"] == ""
    assert d["country"] == "United States"
    assert isinstance(d["experience"], list)


def test_put_then_get_persists(client):
    payload = {
        "first_name": "Alex", "last_name": "Doe",
        "email": "test@example.com", "school": "Test University",
        "school_gpa": "3.9", "work_auth_us": "Yes",
    }
    r = client.put("/api/profile", json=payload)
    assert r.status_code == 200

    # Re-fetch and confirm
    r2 = client.get("/api/profile").json()
    assert r2["first_name"] == "Alex"
    assert r2["email"] == "test@example.com"
    assert r2["school"] == "Test University"
    assert r2["work_auth_us"] == "Yes"


def test_partial_update_preserves_other_fields(client):
    client.put("/api/profile", json={"first_name": "Alice", "email": "a@x.com"})
    client.put("/api/profile", json={"phone": "(555) 123-4567"})
    d = client.get("/api/profile").json()
    assert d["first_name"] == "Alice"      # unchanged
    assert d["email"] == "a@x.com"          # unchanged
    assert d["phone"] == "(555) 123-4567"   # updated


def test_json_blob_fields_round_trip(client):
    skills = ["Python", "PyTorch", "AWS"]
    exp = [{"title": "Intern", "company": "X", "startDate": "2024-06"}]
    client.put("/api/profile", json={"skills": skills, "experience": exp})
    d = client.get("/api/profile").json()
    assert d["skills"] == skills
    assert d["experience"] == exp
