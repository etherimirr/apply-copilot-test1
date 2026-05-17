"""Unit tests for audit's pure scoring functions (no LLM)."""
from __future__ import annotations
from apply_copilot.core.audit import (
    _compute_raw_coverage, _compute_addressable_coverage,
)


def _kws(n: int) -> list[dict]:
    return [{"keyword": f"k{i}", "importance": "med", "type": "tool"} for i in range(n)]


def test_raw_coverage_empty_keywords():
    assert _compute_raw_coverage({}, []) == 0


def test_raw_coverage_all_explicit():
    cls = {"explicit": [{"keyword": "k0"}, {"keyword": "k1"}],
           "implicit": [], "missing": []}
    assert _compute_raw_coverage(cls, _kws(2)) == 100


def test_raw_coverage_mixed():
    cls = {"explicit": [{"keyword": "k0"}], "implicit": [{"keyword": "k1"}],
           "missing": [{"keyword": "k2"}, {"keyword": "k3"}]}
    # 2 covered of 4 -> 50%
    assert _compute_raw_coverage(cls, _kws(4)) == 50


def test_addressable_excludes_no_fix():
    """If 2 of 4 are no_fix (irrelevant industry), addressable = 4-2 = 2."""
    cls = {"explicit": [{"keyword": "k0"}, {"keyword": "k1"}], "implicit": [],
           "missing": [{"keyword": "k2", "no_fix": True},
                        {"keyword": "k3", "no_fix": True}]}
    # 2/2 addressable = 100%
    assert _compute_addressable_coverage(cls, _kws(4)) == 100


def test_addressable_floor_prevents_gaming():
    """Bug Christina hit: 1 of 22 explicit, 21 marked no_fix → addressable
    would round to 100%, but the score should reflect the raw 5% — the
    floor kicks in when raw < 30 but pct > 80."""
    cls = {
        "explicit": [{"keyword": "k0"}], "implicit": [],
        "missing": [{"keyword": f"k{i}", "no_fix": True} for i in range(1, 22)],
    }
    # raw = 1/22 = 5%, addressable_pre = 1/1 = 100% — floor returns raw
    assert _compute_addressable_coverage(cls, _kws(22)) == 5


def test_addressable_empty():
    assert _compute_addressable_coverage({}, []) == 0


def test_addressable_no_no_fix_matches_raw():
    cls = {"explicit": [{"keyword": "k0"}], "implicit": [{"keyword": "k1"}],
           "missing": [{"keyword": "k2", "no_fix": False},
                        {"keyword": "k3", "no_fix": False}]}
    # 2/4 = 50%, no no_fix -> addressable = raw
    assert _compute_addressable_coverage(cls, _kws(4)) == 50
