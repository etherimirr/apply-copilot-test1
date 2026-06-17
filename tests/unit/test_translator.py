"""Unit tests for translator (offline parts only).

The actual LLM translation path is exercised by integration tests with a
real API key. Here we test:
- Language detection
- Keep-token extraction (URLs, emails, percentages, dates, tech terms)
- Run redistribution mechanics (no LLM)
"""
from __future__ import annotations
import pytest

from apply_copilot.core.translator import (
    detect_lang, _KEEP_TOKEN_RE, PRESERVE_TERMS,
    _redistribute_runs, translate_docx,
)


@pytest.mark.parametrize("text,expected", [
    ("", "en"),
    ("Hello world this is English text", "en"),
    ("你好世界这是中文文本足够长以触发检测", "zh"),
    ("Built a recommendation system using Python", "en"),
    # Mixed but dominantly Chinese
    ("使用 Python 构建了推荐系统，服务 40K 用户，吞吐量提升 20%", "zh"),
])
def test_detect_lang(text, expected):
    assert detect_lang(text) == expected


@pytest.mark.parametrize("text,token", [
    ("Email me at jane@example.com", "jane@example.com"),
    ("My GitHub: https://github.com/jane", "https://github.com/jane"),
    ("Achieved 99.9% uptime", "99.9"),
    ("Reduced latency 60%", "60%"),
    ("Worked from Jul 2025 to Aug 2025", "Jul 2025"),
    ("2024-2026 internship", "2024-2026"),
])
def test_keep_token_re(text, token):
    matches = [m.strip() for m in _KEEP_TOKEN_RE.findall(text)]
    assert token in matches, f"expected {token!r} in {matches}"


def test_preserve_terms_contains_common_techs():
    """Sanity check: the preserve list has the obvious culprits."""
    for term in ["Python", "PyTorch", "Docker", "AWS", "LLM"]:
        assert term in PRESERVE_TERMS


def test_redistribute_runs_basic():
    """Simulate a 3-run paragraph; translated text goes to run 0, others blank."""
    class FakeRun:
        def __init__(self, text):
            self.text = text

    runs = [FakeRun("Built a "), FakeRun("recommendation"), FakeRun(" system")]
    _redistribute_runs(runs, "构建了推荐系统")
    assert runs[0].text == "构建了推荐系统"
    assert runs[1].text == ""
    assert runs[2].text == ""


def test_redistribute_runs_ignores_empty():
    """Empty runs in the middle shouldn't break redistribution."""
    class FakeRun:
        def __init__(self, text):
            self.text = text

    runs = [FakeRun(""), FakeRun("Built"), FakeRun(" system")]
    _redistribute_runs(runs, "构建了系统")
    assert runs[0].text == ""
    assert runs[1].text == "构建了系统"
    assert runs[2].text == ""


def test_redistribute_runs_all_empty_is_noop():
    """If all runs are empty, redistribute does nothing (no crash)."""
    class FakeRun:
        def __init__(self, text):
            self.text = text

    runs = [FakeRun(""), FakeRun(""), FakeRun("")]
    _redistribute_runs(runs, "anything")
    assert all(r.text == "" for r in runs)


def test_translate_docx_same_lang_skips(tmp_path):
    """source_lang == target_lang → 0 translated, no LLM calls."""
    from docx import Document
    doc = Document()
    doc.add_paragraph("Hello world this is English text")
    result = translate_docx(doc, target_lang="en", source_lang="en")
    assert result["translated"] == 0
    assert result["source_lang"] == "en"
    assert result["target_lang"] == "en"


def test_translate_docx_bad_target_lang_raises():
    from docx import Document
    doc = Document()
    doc.add_paragraph("hi")
    with pytest.raises(ValueError):
        translate_docx(doc, target_lang="fr")
