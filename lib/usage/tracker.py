"""
Usage tracking and quota management for API requests.
"""

import os
from datetime import datetime
from typing import Dict, Optional
from lib.db.connection import get_db
from lib.db.models import User, Usage, GlobalUsage

# Free tier limit from environment (default: 5 requests)
FREE_TIER_LIMIT = int(os.getenv("FREE_TIER_LIMIT", "5"))


def check_anonymous_usage() -> bool:
    """
    Check if anonymous usage is under the free tier limit.

    Returns:
        True if anonymous user can make another request, False otherwise
    """
    with get_db() as db:
        global_usage = db.query(GlobalUsage).first()

        if not global_usage:
            # Create initial record if it doesn't exist
            global_usage = GlobalUsage(id=1, anonymous_count=0)
            db.add(global_usage)
            db.commit()
            return True

        return global_usage.anonymous_count < FREE_TIER_LIMIT


def increment_anonymous_usage() -> None:
    """
    Increment the global anonymous usage counter.
    """
    with get_db() as db:
        global_usage = db.query(GlobalUsage).first()

        if not global_usage:
            # Create initial record
            global_usage = GlobalUsage(id=1, anonymous_count=1)
            db.add(global_usage)
        else:
            # Increment counter
            global_usage.anonymous_count += 1

        db.commit()


def check_user_usage(user_id: int) -> bool:
    """
    Check if authenticated user is under their quota.

    For now, authenticated users have unlimited access.
    Future: implement per-user quotas, paid tiers, etc.

    Args:
        user_id: User ID from database

    Returns:
        True if user can make another request (always True for now)
    """
    # Authenticated users have unlimited access
    return True


def increment_user_usage(user_id: int) -> None:
    """
    Increment the request counter for an authenticated user.

    Args:
        user_id: User ID from database
    """
    with get_db() as db:
        usage = db.query(Usage).filter(Usage.user_id == user_id).first()

        if not usage:
            # Create new usage record
            usage = Usage(
                user_id=user_id,
                request_count=1,
                last_request=datetime.utcnow()
            )
            db.add(usage)
        else:
            # Increment counter and update timestamp
            usage.request_count += 1
            usage.last_request = datetime.utcnow()

        db.commit()


def get_usage_stats(user_id: Optional[int] = None) -> Dict:
    """
    Get usage statistics for a user or anonymous users.

    Args:
        user_id: User ID (None for anonymous stats)

    Returns:
        Dictionary with usage statistics:
        {
            "requests_used": int,
            "quota_limit": int | "unlimited",
            "is_authenticated": bool
        }
    """
    with get_db() as db:
        if user_id:
            # Get authenticated user stats
            usage = db.query(Usage).filter(Usage.user_id == user_id).first()
            return {
                "requests_used": usage.request_count if usage else 0,
                "quota_limit": "unlimited",  # For now
                "is_authenticated": True
            }
        else:
            # Get anonymous usage stats
            global_usage = db.query(GlobalUsage).first()
            return {
                "requests_used": global_usage.anonymous_count if global_usage else 0,
                "quota_limit": FREE_TIER_LIMIT,
                "is_authenticated": False
            }


def reset_anonymous_usage() -> None:
    """
    Reset the global anonymous usage counter to zero.
    Useful for testing or periodic resets.
    """
    with get_db() as db:
        global_usage = db.query(GlobalUsage).first()

        if global_usage:
            global_usage.anonymous_count = 0
            db.commit()
