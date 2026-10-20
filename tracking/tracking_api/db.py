"""Database session management.

Deliberately a thin local engine rather than ``radar_db.db_manager``: that
singleton reads its connection settings from ``radar_db.config``, which expects
its own environment variable names. Building the engine here keeps this
service's configuration in one place (``tracking_api.config``) while still
reusing the shared ORM models from ``radar_db.models``.
"""

from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import QueuePool

from tracking_api.config import settings

_engine = create_engine(
    settings.database_url,
    poolclass=QueuePool,
    pool_size=5,
    max_overflow=5,
    pool_pre_ping=True,
    pool_recycle=300,
    echo=False,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_engine)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a session."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    """Session for code outside the request cycle (background job runner)."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def check_connection() -> bool:
    """True if the database answers. Used by /health."""
    from sqlalchemy import text

    try:
        with _engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
