"""
Usage tracking and quota management for API requests.

When the database is not configured (POSTGRES_URL not set) all usage checks
pass unconditionally and increment calls are silently skipped.  This lets the
demo deployment work without a database.
"""

import os
from datetime import datetime
from typing import Dict, Optional
from lib.db.connection import get_db, DB_AVAILABLE
from lib.db.models import User, Usage, GlobalUsage

FREE_TIER_LIMIT = int(os.getenv("FREE_TIER_LIMIT", "5"))


def check_anonymous_usage() -> bool:
    """Return True if anonymous usage is under the free tier limit."""
    if not DB_AVAILABLE:
        return True  # no DB → allow all requests in demo mode

    try:
        with get_db() as db:
            global_usage = db.query(GlobalUsage).first()
            if not global_usage:
                global_usage = GlobalUsage(id=1, anonymous_count=0)
                db.add(global_usage)
                db.commit()
                return True
            return global_usage.anonymous_count < FREE_TIER_LIMIT
    except Exception as e:
        print(f"Usage check error: {e}")
        return True  # fail open


def increment_anonymous_usage() -> None:
    """Increment the global anonymous usage counter."""
    if not DB_AVAILABLE:
        return

    try:
        with get_db() as db:
            global_usage = db.query(GlobalUsage).first()
            if not global_usage:
                global_usage = GlobalUsage(id=1, anonymous_count=1)
                db.add(global_usage)
            else:
                global_usage.anonymous_count += 1
            db.commit()
    except Exception as e:
        print(f"Usage increment error: {e}")


def check_user_usage(user_id: int) -> bool:
    """Authenticated users have unlimited access."""
    return True


def increment_user_usage(user_id: int) -> None:
    """Increment the request counter for an authenticated user."""
    if not DB_AVAILABLE:
        return

    try:
        with get_db() as db:
            usage = db.query(Usage).filter(Usage.user_id == user_id).first()
            if not usage:
                usage = Usage(
                    user_id=user_id,
                    request_count=1,
                    last_request=datetime.utcnow(),
                )
                db.add(usage)
            else:
                usage.request_count += 1
                usage.last_request = datetime.utcnow()
            db.commit()
    except Exception as e:
        print(f"User usage increment error: {e}")


def get_usage_stats(user_id: Optional[int] = None) -> Dict:
    """Get usage statistics for a user or anonymous users."""
    if not DB_AVAILABLE:
        return {
            "requests_used": 0,
            "quota_limit": "unlimited",
            "is_authenticated": user_id is not None,
        }

    try:
        with get_db() as db:
            if user_id:
                usage = db.query(Usage).filter(Usage.user_id == user_id).first()
                return {
                    "requests_used": usage.request_count if usage else 0,
                    "quota_limit": "unlimited",
                    "is_authenticated": True,
                }
            else:
                global_usage = db.query(GlobalUsage).first()
                return {
                    "requests_used": global_usage.anonymous_count if global_usage else 0,
                    "quota_limit": FREE_TIER_LIMIT,
                    "is_authenticated": False,
                }
    except Exception as e:
        print(f"Usage stats error: {e}")
        return {
            "requests_used": 0,
            "quota_limit": FREE_TIER_LIMIT,
            "is_authenticated": user_id is not None,
        }


def reset_anonymous_usage() -> None:
    """Reset the global anonymous usage counter to zero (useful for testing)."""
    if not DB_AVAILABLE:
        return

    try:
        with get_db() as db:
            global_usage = db.query(GlobalUsage).first()
            if global_usage:
                global_usage.anonymous_count = 0
                db.commit()
    except Exception as e:
        print(f"Usage reset error: {e}")
