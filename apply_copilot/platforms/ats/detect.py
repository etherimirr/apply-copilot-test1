"""ATS fingerprint: URL → canonical name."""
from __future__ import annotations
from urllib.parse import urlparse


URL_FINGERPRINTS = [
    ("workday", ["myworkdayjobs.com", ".workdayjobs.com", "workday.com"]),
    ("greenhouse", ["boards.greenhouse.io", "job-boards.greenhouse.io",
                    "greenhouse.io/jobs"]),
    ("lever", ["jobs.lever.co", "lever.co/postings"]),
    ("ashby", ["jobs.ashbyhq.com", "ashbyhq.com"]),
    ("icims", ["icims.com"]),
    ("jobvite", ["jobvite.com"]),
    ("smartrecruiters", ["smartrecruiters.com"]),
    ("personio", ["personio.com/jobs"]),
    ("pinpoint", ["pinpointhq.com"]),
    ("bamboohr", ["bamboohr.com"]),
    ("paylocity", ["paylocity.com"]),
    ("ukg", ["ukg.com/careers", ".ultipro.com"]),
    ("teamtailor", ["teamtailor.com"]),
    ("breezy", ["breezy.hr"]),
    ("rippling", ["ats.rippling.com"]),
    ("recruitee", ["recruitee.com"]),
    ("taleo", ["taleo.net"]),
    ("amazon", ["amazon.jobs"]),
    ("google", ["careers.google.com"]),
    ("meta", ["metacareers.com"]),
    ("apple", ["jobs.apple.com"]),
    ("microsoft", ["careers.microsoft.com"]),
    ("netflix", ["jobs.netflix.com"]),
    ("handshake", ["joinhandshake.com"]),
]


def detect_ats(url: str) -> str:
    """Returns canonical ATS name, or 'generic' if no fingerprint matches."""
    if not url:
        return "generic"
    host = (urlparse(url).hostname or "").lower()
    full = url.lower()
    for name, patterns in URL_FINGERPRINTS:
        for p in patterns:
            if p in host or p in full:
                return name
    return "generic"
