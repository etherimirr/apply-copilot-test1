"""SQLAlchemy models. Single-user for now; profile is a single-row table."""
from __future__ import annotations
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, JSON, ForeignKey
from sqlalchemy.orm import declarative_base, relationship


Base = declarative_base()


class Profile(Base):
    """User's personal info — single row, id=1."""
    __tablename__ = "profile"
    id = Column(Integer, primary_key=True)
    # Identity
    first_name = Column(String, default="")
    last_name = Column(String, default="")
    preferred_name = Column(String, default="")
    pronouns = Column(String, default="")
    email = Column(String, default="")
    phone = Column(String, default="")
    phone_country_code = Column(String, default="+1")
    birth_date = Column(String, default="")  # YYYY-MM-DD
    # Address
    address1 = Column(String, default="")
    address2 = Column(String, default="")
    city = Column(String, default="")
    state = Column(String, default="")
    postal_code = Column(String, default="")
    country = Column(String, default="United States")
    # Online
    linkedin = Column(String, default="")
    github = Column(String, default="")
    portfolio = Column(String, default="")
    # Education (current)
    school = Column(String, default="")
    school_degree = Column(String, default="")
    school_major = Column(String, default="")
    school_gpa = Column(String, default="")
    school_start_date = Column(String, default="")
    school_end_date = Column(String, default="")
    graduation_date = Column(String, default="")
    # Work auth
    work_auth_us = Column(String, default="Yes")
    need_sponsorship = Column(String, default="No")
    willing_to_relocate = Column(String, default="Yes")
    salary_expectation = Column(String, default="")
    available_start_date = Column(String, default="")
    # Demographics (optional, all "Decline to answer" by default)
    gender = Column(String, default="Decline to answer")
    race = Column(String, default="Decline to answer")
    ethnicity = Column(String, default="Decline to answer")
    veteran = Column(String, default="No")
    disability = Column(String, default="No")
    lgbtq = Column(String, default="Decline to answer")
    years_of_experience = Column(String, default="0")
    summary = Column(Text, default="")
    # JSON blobs for richer data
    experience = Column(JSON, default=list)        # list[{title, company, ...}]
    education = Column(JSON, default=list)         # list[{school, degree, ...}]
    skills = Column(JSON, default=list)            # list[str]
    project_kb = Column(JSON, default=dict)        # {project_id: markdown text}

    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Resume(Base):
    """One row per uploaded base resume. User can upload multiple 'direction'
    versions (e.g. ML / SDE / Generalist) and the autopilot picks per JD."""
    __tablename__ = "resume"
    id = Column(Integer, primary_key=True)
    direction = Column(String, nullable=False)     # e.g. "mle", "sde_general"
    label = Column(String, default="")             # human label
    filename = Column(String, nullable=False)      # filename in RESUMES_DIR
    is_default = Column(Boolean, default=False)    # used when direction lookup fails
    uploaded_at = Column(DateTime, default=datetime.utcnow)


class Submission(Base):
    """One row per submission event (submit / withdraw / re-submit)."""
    __tablename__ = "submission"
    id = Column(Integer, primary_key=True)
    bundle_slug = Column(String, nullable=False, index=True)  # company__title slug
    company = Column(String, default="")
    title = Column(String, default="")
    url = Column(String, default="")
    platform = Column(String, default="handshake")   # handshake | greenhouse | lever | ...
    employment_type = Column(String, default="intern")  # intern | fulltime
    direction = Column(String, default="")           # which resume direction
    resume_filename = Column(String, default="")     # filename that was uploaded
    status = Column(String, default="submitted")     # submitted | external_pending | withdrawn | gate_fail
    coverage_pct = Column(Integer, default=0)        # addressable coverage at submit time
    submitted_at = Column(DateTime, default=datetime.utcnow)
    withdrawn_at = Column(DateTime, nullable=True)
    notes = Column(Text, default="")


class BundleState(Base):
    """Per-bundle UI state — checked, notes, deferred, etc."""
    __tablename__ = "bundle_state"
    bundle_slug = Column(String, primary_key=True)
    checked = Column(Boolean, default=False)
    notes = Column(Text, default="")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
