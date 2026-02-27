"""
FastAPI authentication middleware and dependencies.
"""

from fastapi import Depends, HTTPException, Cookie
from sqlalchemy.orm import Session
from typing import Optional
from lib.auth.jwt import verify_token
from lib.db.connection import get_db_dependency
from lib.db.models import User


def get_current_user(
    access_token: Optional[str] = Cookie(None),
    db: Session = Depends(get_db_dependency)
) -> User:
    """
    FastAPI dependency to get the current authenticated user.
    Raises 401 if not authenticated or token is invalid.

    Usage:
        @app.get("/api/protected")
        def protected_route(user: User = Depends(get_current_user)):
            return {"user_id": user.id}
    """
    if not access_token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    # Verify JWT token
    payload = verify_token(access_token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    # Get user from database
    user_id = payload.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    return user


def optional_user(
    access_token: Optional[str] = Cookie(None),
    db: Session = Depends(get_db_dependency)
) -> Optional[User]:
    """
    FastAPI dependency to optionally get the current authenticated user.
    Returns None if not authenticated (does not raise exception).

    Usage:
        @app.get("/api/optional")
        def optional_route(user: Optional[User] = Depends(optional_user)):
            if user:
                return {"authenticated": True, "user_id": user.id}
            return {"authenticated": False}
    """
    if not access_token:
        return None

    # Verify JWT token
    payload = verify_token(access_token)
    if not payload:
        return None

    # Get user from database
    user_id = payload.get("user_id")
    if not user_id:
        return None

    user = db.query(User).filter(User.id == user_id).first()
    return user
