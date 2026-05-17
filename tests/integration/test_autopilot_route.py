"""Integration: autopilot start endpoint guards on env, status returns sane defaults."""
from __future__ import annotations
import os
import pytest


def test_status_when_not_running(client):
    assert client.get("/api/autopilot/status").json() == {"running": False}


def test_start_requires_openai_key(client, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    r = client.post("/api/autopilot/start", json={
        "platform": "handshake", "employment_type": "intern",
        "sort": "newest", "max_jobs": 10, "external_mode": "skip",
    })
    assert r.status_code == 400
    assert "OPENAI_API_KEY" in r.json()["detail"]


def test_start_rejects_unknown_platform(client, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    r = client.post("/api/autopilot/start", json={
        "platform": "linkedin", "max_jobs": 1,
    })
    assert r.status_code == 400


def test_log_endpoint_when_no_run(client):
    """Tail returns empty list when no autopilot has been started yet."""
    r = client.get("/api/autopilot/log")
    assert r.status_code == 200
    assert r.json() == {"lines": []}
