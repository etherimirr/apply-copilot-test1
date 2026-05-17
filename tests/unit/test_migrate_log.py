"""Tests for SUBMITTED_LOG.md → SQLite migration parser."""
from __future__ import annotations
from apply_copilot.storage.migrate_log import parse_log, _slug


SAMPLE_LOG = """# 投递日志

---

## 已提交（按时间倒序）

### ✅ 2026-05-12 — Instalily (Software Engineer, 2026)
- **Source**: 公司官网 portal (portal.instalily.ai)
- **URL**: https://portal.instalily.ai/jobs/software-engineer-2026
- **Resume**: `Christina_Agent_v2.pdf` (Agent base) — base chosen correctly
- **Status**: submitted
- **Notes**: NYC FT, sponsorship pending
---

### 🔌 2026-05-10 — Acme Corp (ML Engineer Intern)
- **Source**: Handshake
- **URL**: https://app.joinhandshake.com/jobs/12345
- **Resume**: `Christina_MLE.pdf` (mle base)
- **Status**: external pending
---

### ⛔ 2026-05-08 — Other Co (Backend Engineer)
- **URL**: https://example.com/job/678
- **Status**: gate_fail
"""


def test_parse_log_block_count():
    blocks = parse_log(SAMPLE_LOG)
    assert len(blocks) == 3


def test_parse_log_company_title():
    blocks = parse_log(SAMPLE_LOG)
    assert blocks[0]["company"] == "Instalily"
    assert blocks[0]["title"] == "Software Engineer, 2026"
    assert blocks[1]["company"] == "Acme Corp"
    assert blocks[1]["title"] == "ML Engineer Intern"


def test_parse_log_url_extracted():
    blocks = parse_log(SAMPLE_LOG)
    assert blocks[0]["url"] == "https://portal.instalily.ai/jobs/software-engineer-2026"
    assert blocks[1]["url"] == "https://app.joinhandshake.com/jobs/12345"


def test_parse_log_status_normalized():
    blocks = parse_log(SAMPLE_LOG)
    assert blocks[0]["status"] == "submitted"
    assert blocks[1]["status"] == "external_pending"
    assert blocks[2]["status"] == "gate_fail"


def test_parse_log_resume_filename_and_direction():
    blocks = parse_log(SAMPLE_LOG)
    assert blocks[0]["resume_filename"] == "Christina_Agent_v2.pdf"
    assert blocks[0]["direction"] == "agent"
    assert blocks[1]["resume_filename"] == "Christina_MLE.pdf"
    assert blocks[1]["direction"] == "mle"


def test_parse_log_platform_handshake_detected():
    blocks = parse_log(SAMPLE_LOG)
    assert blocks[1]["platform"] == "handshake"


def test_parse_log_notes_captured():
    blocks = parse_log(SAMPLE_LOG)
    assert "NYC FT" in blocks[0]["notes"]


def test_slug_normalizes():
    assert _slug("Acme Corp", "ML Engineer Intern") == "acme_corp_ml_engineer_intern"
    assert _slug("Foo, Inc.", "Senior SWE / III") == "foo_inc_senior_swe_iii"


def test_import_to_sqlite_round_trip(tmp_path, monkeypatch):
    """End-to-end: parse + write + read back."""
    import importlib, os
    monkeypatch.setenv("APPLY_COPILOT_HOME", str(tmp_path / ".apply_copilot"))
    import apply_copilot.config
    import apply_copilot.storage.db
    import apply_copilot.storage.models
    importlib.reload(apply_copilot.config)
    importlib.reload(apply_copilot.storage.db)
    importlib.reload(apply_copilot.storage.models)
    # Re-import migrate_log to pick up reloaded modules
    import apply_copilot.storage.migrate_log
    importlib.reload(apply_copilot.storage.migrate_log)
    blocks = apply_copilot.storage.migrate_log.parse_log(SAMPLE_LOG)
    result = apply_copilot.storage.migrate_log.import_to_sqlite(blocks)
    assert result["added"] == 3
    # Re-running should add zero (idempotent on URL+submitted match)
    result2 = apply_copilot.storage.migrate_log.import_to_sqlite(blocks)
    # Only the first ("submitted") row is deduped; the others have different statuses
    assert result2["added"] == 2  # external_pending and gate_fail aren't dedup'd
