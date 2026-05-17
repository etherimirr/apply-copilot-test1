"""Unit: detect_ats — URL → canonical ATS name."""
from __future__ import annotations
import pytest

from apply_copilot.platforms.ats.detect import detect_ats


@pytest.mark.parametrize("url,expected", [
    ("https://boards.greenhouse.io/foocompany/jobs/123", "greenhouse"),
    ("https://job-boards.greenhouse.io/bar/jobs/45", "greenhouse"),
    ("https://jobs.lever.co/baz/abc-def", "lever"),
    ("https://acme.myworkdayjobs.com/external/job/123", "workday"),
    ("https://jobs.ashbyhq.com/co/role-x", "ashby"),
    ("https://careers-icims.com/job/...", "icims"),
    ("https://amazon.jobs/en/jobs/123", "amazon"),
    ("https://careers.google.com/jobs/...", "google"),
    ("https://app.joinhandshake.com/jobs/11044939", "handshake"),
    ("", "generic"),
    ("https://random-company-careers.example.com/apply/42", "generic"),
])
def test_detect_known(url, expected):
    assert detect_ats(url) == expected


def test_handshake_apply_externally_url():
    assert detect_ats("https://app.joinhandshake.com/jobs/123") == "handshake"


def test_case_insensitive():
    assert detect_ats("HTTPS://JOBS.LEVER.CO/ACME/X") == "lever"
