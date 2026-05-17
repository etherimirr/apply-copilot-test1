"""Classify a form field (label / name / placeholder text) into a canonical
field type, then resolve its value from the user profile.

Label-driven heuristics let one filler handle Greenhouse / Lever / Ashby /
generic external-apply forms without per-ATS code paths.
"""
from __future__ import annotations
import re
from typing import Optional

FIELD_TYPES = {
    "first_name", "last_name", "full_name", "preferred_name", "pronouns",
    "email", "phone", "phone_country", "birth_date",
    "address1", "address2", "city", "state", "postal_code", "country", "location",
    "linkedin", "github", "portfolio", "website",
    "school", "degree", "field_of_study", "gpa", "grad_date", "grad_month", "grad_year",
    "school_start_date", "school_end_date",
    "work_auth_us", "needs_sponsorship", "willing_to_relocate", "salary_expectation",
    "available_start_date",
    "gender", "race", "ethnicity", "veteran", "disability", "lgbtq",
    "years_experience", "current_company", "current_title",
    "resume", "cover_letter", "transcript", "portfolio_file",
    "summary", "open_question", "skip",
}


# (canonical_type, regex patterns, profile_key) — order matters, specific first.
LABEL_RULES: list[tuple[str, list[str], Optional[str]]] = [
    ("first_name", [r"\bfirst[\s-]*name\b", r"\bgiven[\s-]*name\b"], "first_name"),
    ("last_name", [r"\blast[\s-]*name\b", r"\bsurname\b", r"\bfamily[\s-]*name\b"], "last_name"),
    ("preferred_name", [r"\bpreferred[\s-]*(name|first[\s-]*name)\b", r"\bnickname\b"], "preferred_name"),
    ("full_name", [r"^name$", r"^full[\s-]*name$", r"\bcandidate[\s-]*name\b"], "full_name"),
    ("pronouns", [r"\bpronouns?\b"], "pronouns"),

    ("email", [r"\bemail\b", r"e[\s-]*mail address"], "email"),
    ("phone_country", [r"country[\s-]*code", r"phone[\s-]*country"], "phone_country_code"),
    ("phone", [r"\bphone\b", r"mobile[\s-]*number", r"telephone"], "phone"),
    ("birth_date", [r"\bbirthday\b", r"\bdate[\s-]*of[\s-]*birth\b", r"\bdob\b"], "birth_date"),

    ("postal_code", [r"\bzip\b", r"\bpostal[\s-]*code\b"], "postal_code"),
    ("state", [r"\bstate\b", r"\bprovince\b", r"\bregion\b"], "state"),
    ("city", [r"\bcity\b"], "city"),
    ("country", [r"\bcountry\b"], "country"),
    ("address2", [r"address.*line.*2", r"\bapt\b", r"\bunit\b", r"\bsuite\b"], "address2"),
    ("address1", [r"\baddress\b", r"street", r"address.*line.*1"], "address1"),
    ("location", [r"\blocation\b", r"\bcurrent location\b", r"\bwhere are you\b",
                  r"\bcity, state\b"], "location"),

    ("linkedin", [r"\blinkedin\b", r"linked[\s-]*in.*url",
                  r"\blinked[\s-]*in profile\b"], "linkedin"),
    ("github", [r"\bgithub\b", r"git[\s-]*hub.*url",
                r"\bgit[\s-]*hub profile\b", r"\bgitlab\b"], "github"),
    ("portfolio", [r"\bportfolio\b.*(url|link|site)", r"personal\s*website",
                   r"\bwebsite\b", r"\bpersonal\s*site\b",
                   r"\bproject site\b", r"\bblog\b"], "portfolio"),

    ("school", [r"\b(school|university|college|institution)\b"], "school"),
    ("degree", [r"\bdegree\b", r"degree level"], "school_degree"),
    ("field_of_study", [r"\bmajor\b", r"\bfield of study\b", r"\bdiscipline\b"], "school_major"),
    ("gpa", [r"\bgpa\b", r"\bgrade point average\b"], "school_gpa"),
    ("grad_date", [r"graduation.*(date|year)", r"expected\s*graduation",
                   r"\bend\s*date\b.*(school|education)"], "graduation_date"),
    ("grad_month", [r"graduation.*month"], "graduation_month"),
    ("grad_year", [r"graduation.*year"], "graduation_year"),

    # Work-auth MUST come before address2 (which catches "unit" in "United States")
    ("work_auth_us", [r"authoriz", r"work.*authorization", r"legally.*authorized",
                      r"\beligible to work\b", r"work.*united states",
                      r"\bright to work\b", r"\blegally able to work\b"], "work_auth_us"),
    ("needs_sponsorship", [r"require.*sponsor", r"need.*sponsor", r"visa.*sponsor",
                           r"\bh-?1b\b", r"\bemployment authorization\b",
                           r"\bvisa status\b", r"work visa"], "need_sponsorship"),
    ("willing_to_relocate", [r"willing to relocate", r"relocation",
                              r"\bopen to relocation\b"], "willing_to_relocate"),
    ("salary_expectation", [r"salary.*expect", r"expected.*salary", r"compensation.*expect",
                            r"desired.*salary", r"\bsalary range\b",
                            r"\bsalary requirement", r"hourly rate"], "salary_expectation"),
    ("available_start_date", [r"available.*start", r"earliest.*start", r"start date",
                               r"when can you start", r"\bnotice period\b"],
     "available_start_date"),

    ("gender", [r"\bgender\b"], "gender"),
    ("race", [r"\brace\b"], "race"),
    ("ethnicity", [r"ethnic", r"hispanic.*latino"], "ethnicity"),
    ("veteran", [r"\bveteran\b", r"military.*service"], "veteran"),
    ("disability", [r"disabilit"], "disability"),
    ("lgbtq", [r"\blgbt", r"sexual orientation"], "lgbtq"),

    ("years_experience", [r"years.*experience", r"experience.*years",
                           r"\byoe\b", r"years of relevant"], "years_of_experience"),
    ("current_company", [r"current.*employer", r"current.*company",
                          r"most recent employer"], None),
    ("current_title", [r"current.*title", r"current.*position", r"current.*role",
                        r"job title"], None),

    ("resume", [r"\bresume\b", r"\bcv\b", r"upload.*resume"], None),
    ("cover_letter", [r"cover.?letter"], None),
    ("transcript", [r"transcript"], None),
    ("portfolio_file", [r"upload.*portfolio", r"portfolio.*file"], None),

    ("summary", [r"\bsummary\b", r"\babout (you|me)\b", r"tell us about yourself.*brief"],
     "summary"),
]


def classify_field(label: str, name: str = "", placeholder: str = "",
                   aria_label: str = "", input_type: str = "") -> Optional[tuple[str, Optional[str]]]:
    """Return (canonical_type, profile_key) or None if unclassified."""
    haystack = " ".join(filter(None, [label, name, placeholder, aria_label])).lower()
    haystack = re.sub(r"[*]", "", haystack)
    haystack = re.sub(r"\s+", " ", haystack).strip()
    if not haystack:
        return None
    if input_type == "file":
        if re.search(r"resume|\bcv\b", haystack):
            return ("resume", None)
        if re.search(r"cover.?letter", haystack):
            return ("cover_letter", None)
        if re.search(r"transcript", haystack):
            return ("transcript", None)
        if re.search(r"portfolio", haystack):
            return ("portfolio_file", None)
        return ("resume", None)
    for canonical, patterns, key in LABEL_RULES:
        if any(re.search(p, haystack, re.I) for p in patterns):
            return (canonical, key)
    return None


def value_for(canonical: str, profile: dict, profile_key: Optional[str] = None) -> str:
    """Resolve the actual value to fill from a (possibly nested) profile dict."""
    if profile_key:
        val = profile.get(profile_key)
        if val is not None and val != "":
            return str(val)
    if canonical == "summary":
        return profile.get("summary", "")
    return ""


def is_demographic(canonical: str) -> bool:
    """Demographic questions are typically optional; users can configure to skip."""
    return canonical in {"race", "ethnicity", "veteran", "disability", "lgbtq"}
