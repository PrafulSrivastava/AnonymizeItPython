"""
Database connection management for Vercel Postgres.

When sqlalchemy is not installed (or POSTGRES_URL is not set) the module
degrades gracefully: DB_AVAILABLE is False, get_db() raises RuntimeError,
and get_db_dependency() yields None so that optional_user and other optional
FastAPI dependencies can still function without a database.
"""

import os
from contextlib import contextmanager
from typing import Generator, Optional

try:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker, Session as _Session
    _SA_AVAILABLE = True
except ImportError:
    _SA_AVAILABLE = False
    _Session = None  # type: ignore[assignment,misc]

DATABASE_URL = os.getenv("POSTGRES_URL")

if _SA_AVAILABLE and DATABASE_URL:
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
    )
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    DB_AVAILABLE = True
else:
    engine = None
    SessionLocal = None
    DB_AVAILABLE = False
    if not _SA_AVAILABLE:
        print("Warning: sqlalchemy not installed – database features disabled")
    elif not DATABASE_URL:
        print("Warning: POSTGRES_URL not set – database features disabled")


@contextmanager
def get_db():
    """
    Provide a transactional scope around database operations.
    Raises RuntimeError when the database is not configured.
    """
    if not SessionLocal:
        raise RuntimeError("Database not configured. Set POSTGRES_URL (and install sqlalchemy).")

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_db_dependency():
    """
    FastAPI dependency for database sessions.
    Yields None when the database is not configured so that optional
    endpoints can still serve requests without a database.
    """
    if not SessionLocal:
        yield None
        return

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
