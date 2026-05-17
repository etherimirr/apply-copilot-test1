"""SQLite-backed storage. Single file, portable across OSes."""
from __future__ import annotations
from contextlib import contextmanager
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from ..config import SUBMISSIONS_DB, ensure_dirs


_engine = None
_SessionLocal = None


def _get_engine():
    global _engine, _SessionLocal
    if _engine is None:
        ensure_dirs()
        _engine = create_engine(f"sqlite:///{SUBMISSIONS_DB}", future=True,
                                connect_args={"check_same_thread": False})
        _SessionLocal = sessionmaker(bind=_engine, autoflush=False, expire_on_commit=False)
    return _engine


def init_db():
    """Create all tables. Idempotent."""
    from .models import Base
    eng = _get_engine()
    Base.metadata.create_all(eng)


@contextmanager
def get_session() -> Session:
    """Context-managed session: commit on success, rollback on exception."""
    _get_engine()
    s = _SessionLocal()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()
