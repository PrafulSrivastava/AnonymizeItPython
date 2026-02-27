"""
JWT token creation and validation utilities.
"""

from jose import jwt, JWTError
from datetime import datetime, timedelta
import os
from typing import Dict, Optional

# JWT configuration from environment
JWT_SECRET = os.getenv("JWT_SECRET_KEY", "change-this-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = 30


def create_access_token(data: Dict) -> str:
    """
    Create a JWT access token.

    Args:
        data: Dictionary with user data (user_id, email, google_id)

    Returns:
        Encoded JWT token string

    Example:
        token = create_access_token({
            "user_id": 123,
            "email": "user@example.com",
            "google_id": "1234567890"
        })
    """
    to_encode = data.copy()

    # Add expiration time
    expire = datetime.utcnow() + timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)
    to_encode.update({
        "exp": expire,
        "iat": datetime.utcnow()
    })

    # Encode and return
    encoded_jwt = jwt.encode(to_encode, JWT_SECRET, algorithm=ALGORITHM)
    return encoded_jwt


def verify_token(token: str) -> Optional[Dict]:
    """
    Verify and decode a JWT token.

    Args:
        token: JWT token string

    Returns:
        Decoded payload dictionary if valid, None if invalid

    Example:
        payload = verify_token("eyJ...")
        if payload:
            user_id = payload["user_id"]
    """
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[ALGORITHM])
        return payload
    except JWTError as e:
        print(f"JWT verification failed: {e}")
        return None
