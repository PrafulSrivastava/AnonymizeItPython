"""
OAuth provider configuration and initialization.
"""

from authlib.integrations.starlette_client import OAuth
import os

# Initialize OAuth client
oauth = OAuth()

# Google OAuth configuration
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")

if GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET:
    oauth.register(
        name='google',
        client_id=GOOGLE_CLIENT_ID,
        client_secret=GOOGLE_CLIENT_SECRET,
        server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
        client_kwargs={
            'scope': 'openid email profile'
        }
    )
else:
    print("Warning: GOOGLE_CLIENT_ID or GOOGLE_CLIENT_SECRET not set")


# Future: Add more OAuth providers here
# Example for GitHub:
# oauth.register(
#     name='github',
#     client_id=os.getenv("GITHUB_CLIENT_ID"),
#     client_secret=os.getenv("GITHUB_CLIENT_SECRET"),
#     authorize_url='https://github.com/login/oauth/authorize',
#     access_token_url='https://github.com/login/oauth/access_token',
#     client_kwargs={'scope': 'user:email'}
# )
