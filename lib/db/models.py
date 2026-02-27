"""
SQLAlchemy models for user authentication and usage tracking.
"""

from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, CheckConstraint
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func
from datetime import datetime

Base = declarative_base()


class User(Base):
    """User account from OAuth provider."""
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True, autoincrement=True)
    google_id = Column(String(255), unique=True, nullable=False, index=True)
    email = Column(String(255), nullable=False, index=True)
    name = Column(String(255))
    picture_url = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_login = Column(DateTime, default=datetime.utcnow, nullable=False)

    def to_dict(self):
        """Convert user to dictionary."""
        return {
            'id': self.id,
            'email': self.email,
            'name': self.name,
            'picture_url': self.picture_url,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'last_login': self.last_login.isoformat() if self.last_login else None
        }


class Usage(Base):
    """Per-user usage tracking."""
    __tablename__ = 'usage'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), unique=True, nullable=False, index=True)
    request_count = Column(Integer, default=0, nullable=False)
    last_request = Column(DateTime, default=datetime.utcnow, nullable=False)


class GlobalUsage(Base):
    """Global anonymous usage counter (single row table)."""
    __tablename__ = 'global_usage'
    __table_args__ = (
        CheckConstraint('id = 1', name='single_row_constraint'),
    )

    id = Column(Integer, primary_key=True, default=1)
    anonymous_count = Column(Integer, default=0, nullable=False)
