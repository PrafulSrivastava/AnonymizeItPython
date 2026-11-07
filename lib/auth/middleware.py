"""
FastAPI authentication middleware and dependencies.
"""

from fastapi import Depends, HTTPException, Cookie
from typing import Optional, Any
from lib.auth.jwt import verify_token
from lib.db.connection import get_db_dependency, DB_AVAILABLE
from lib.db.models import User


def get_current_user(
    access_token: Optional[str] = Cookie(None),
    db: Optional[Any] = Depends(get_db_dependency),
) -> User:
    """
    FastAPI dependency to get the current authenticated user.
    Raises 401 if not authenticated or token is invalid.
    """
    if not DB_AVAILABLE:
        raise HTTPException(status_code=401, detail="Not authenticated")

    if not access_token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    payload = verify_token(access_token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    user_id = payload.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    return user


def optional_user(
    access_token: Optional[str] = Cookie(None),
    db: Optional[Any] = Depends(get_db_dependency),
) -> Optional[User]:
    """
    FastAPI dependency to optionally get the current authenticated user.
    Returns None if not authenticated or if the database is not configured.
    """
    if not DB_AVAILABLE or not access_token or db is None:
        return None

    payload = verify_token(access_token)
    if not payload:
        return None

    user_id = payload.get("user_id")
    if not user_id:
        return None

    user = db.query(User).filter(User.id == user_id).first()
    return user
