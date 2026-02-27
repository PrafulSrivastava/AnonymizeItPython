"""
Database connection management for Vercel Postgres.
"""

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from contextlib import contextmanager
from typing import Generator

# Get database URL from environment
DATABASE_URL = os.getenv("POSTGRES_URL")

if not DATABASE_URL:
    print("Warning: POSTGRES_URL environment variable not set")
    engine = None
    SessionLocal = None
else:
    # Create SQLAlchemy engine with connection pooling
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,  # Verify connections before using
        pool_size=5,
        max_overflow=10
    )
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@contextmanager
def get_db() -> Generator[Session, None, None]:
    """
    Provide a transactional scope for database operations.

    Usage:
        with get_db() as db:
            user = db.query(User).first()
    """
    if not SessionLocal:
        raise RuntimeError("Database not configured. Set POSTGRES_URL environment variable.")

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_db_dependency():
    """
    FastAPI dependency for database sessions.

    Usage:
        @app.get("/users")
        def get_users(db: Session = Depends(get_db_dependency)):
            return db.query(User).all()
    """
    if not SessionLocal:
        raise RuntimeError("Database not configured. Set POSTGRES_URL environment variable.")

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
