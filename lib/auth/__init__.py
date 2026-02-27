"""
Authentication module for OAuth and JWT handling.
"""

from .jwt import create_access_token, verify_token
from .oauth import oauth
from .middleware import get_current_user, optional_user

__all__ = ['create_access_token', 'verify_token', 'oauth', 'get_current_user', 'optional_user']
