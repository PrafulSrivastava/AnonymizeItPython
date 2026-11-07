"""
Database connection management for Vercel Postgres.

When POSTGRES_URL is not set the module degrades gracefully: DB_AVAILABLE is
False, get_db() raises RuntimeError, and get_db_dependency() yields None so
that optional_user and other optional dependencies can still function.
"""

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from contextlib import contextmanager
from typing import Generator, Optional

DATABASE_URL = os.getenv("POSTGRES_URL")

if DATABASE_URL:
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
    )
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    DB_AVAILABLE = True
else:
    print("Warning: POSTGRES_URL not set – database features disabled")
    engine = None
    SessionLocal = None
    DB_AVAILABLE = False


@contextmanager
def get_db() -> Generator[Session, None, None]:
    """
    Provide a transactional scope around database operations.
    Raises RuntimeError when the database is not configured.
    """
    if not SessionLocal:
        raise RuntimeError("Database not configured. Set POSTGRES_URL environment variable.")

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_db_dependency() -> Generator[Optional[Session], None, None]:
    """
    FastAPI dependency for database sessions.
    Yields None when the database is not configured so that optional
    endpoints can still serve requests without a DB.
    """
    if not SessionLocal:
        yield None
        return

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
