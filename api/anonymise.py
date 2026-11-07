"""
API Entry Point: FastAPI application with Vercel serverless support.
Provides /api/anonymise endpoint for text message anonymization and PII detection.
Supports chat messages, SMS, emails, and any text containing personal information.
Includes OAuth authentication and usage tracking.
"""

# Load environment variables from .env file (must be first!)
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, HTTPException, status, Depends, Cookie, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from mangum import Mangum
from sqlalchemy.orm import Session
from datetime import datetime
from typing import Optional
import os

from lib.types import PipelineInput, AnonymiseResponse, ChatRequest, ChatResponse
from lib.pipeline.index import run_pipeline
from lib.auth.oauth import oauth
from lib.auth.jwt import create_access_token
from lib.auth.middleware import get_current_user, optional_user
from lib.db.connection import get_db_dependency
from lib.db.models import User
from lib.usage.tracker import (
    check_anonymous_usage,
    increment_anonymous_usage,
    check_user_usage,
    increment_user_usage,
    get_usage_stats
)
from lib.workflow.llm_client import OpenAICompatibleClient, LLMError
from lib.workflow.private_chat import run_private_chat, PrivacyRoutingError
from lib.workflow.vault import VaultIntegrityError


# Initialize FastAPI app
app = FastAPI(
    title="Text Anonymization API",
    description="Advanced PII detection and redaction for chat messages, SMS, emails, and text data using NER and ML",
    version="1.0.0"
)

# Add Session middleware (required for OAuth)
# Must be added before CORS middleware
SESSION_SECRET = os.getenv("JWT_SECRET_KEY", "change-this-secret-key-in-production")
app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET,
    session_cookie="session",
    max_age=3600,  # 1 hour session for OAuth flow
    same_site="lax",
    https_only=False  # Set to True in production with HTTPS
)

# CORS: credentials cannot be used with allow_origins=["*"] (browser blocks cross-origin fetch).
_default_origins = "http://localhost:8000,http://127.0.0.1:8000"
_cors_origins = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", _default_origins).split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files for local development
# This allows serving index.html when accessing http://localhost:8000/
try:
    # Get the directory containing this file
    current_dir = os.path.dirname(os.path.abspath(__file__))
    public_dir = os.path.join(os.path.dirname(current_dir), "public")

    if os.path.exists(public_dir):
        # Mount public directory for static files
        app.mount("/static", StaticFiles(directory=public_dir), name="static")
except Exception as e:
    print(f"Note: Static files not mounted (normal for Vercel): {e}")


@app.get("/")
async def root():
    """Serve the frontend HTML or return API info."""
    # Try to serve index.html if it exists (local development)
    try:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        public_dir = os.path.join(os.path.dirname(current_dir), "public")
        index_path = os.path.join(public_dir, "index.html")

        if os.path.exists(index_path):
            return FileResponse(index_path)
    except Exception:
        pass

    # Fallback to API info (for Vercel or if file not found)
    return {
        "status": "ok",
        "service": "Text Anonymization API",
        "version": "1.0.0",
        "description": "PII detection and redaction for chat messages, SMS, emails, and text data"
    }


# Authentication Endpoints

@app.get("/api/auth/login")
async def login(request: Request):
    """
    Initiate Google OAuth login flow.
    Redirects user to Google's authorization page.
    """
    redirect_uri = request.url_for('auth_callback')
    return await oauth.google.authorize_redirect(request, redirect_uri)


@app.get("/api/auth/callback")
async def auth_callback(request: Request, db: Session = Depends(get_db_dependency)):
    """
    Handle Google OAuth callback.
    Creates or updates user record and sets JWT cookie.
    """
    try:
        # Exchange authorization code for access token
        token = await oauth.google.authorize_access_token(request)
        user_info = token.get('userinfo')

        if not user_info:
            raise HTTPException(status_code=400, detail="Failed to get user info from Google")

        # Extract user information
        google_id = user_info.get('sub')
        email = user_info.get('email')
        name = user_info.get('name')
        picture = user_info.get('picture')

        if not google_id or not email:
            raise HTTPException(status_code=400, detail="Incomplete user info from Google")

        # Find existing user or create new one
        user = db.query(User).filter(User.google_id == google_id).first()

        if not user:
            # Create new user
            user = User(
                google_id=google_id,
                email=email,
                name=name,
                picture_url=picture,
                created_at=datetime.utcnow(),
                last_login=datetime.utcnow()
            )
            db.add(user)
            db.commit()
            db.refresh(user)
        else:
            # Update last login time
            user.last_login = datetime.utcnow()
            if name:
                user.name = name
            if picture:
                user.picture_url = picture
            db.commit()

        # Create JWT access token
        access_token = create_access_token({
            "user_id": user.id,
            "email": user.email,
            "google_id": user.google_id
        })

        # Redirect to frontend with secure cookie
        response = RedirectResponse(url="/")
        response.set_cookie(
            key="access_token",
            value=access_token,
            httponly=True,
            max_age=30*24*60*60,  # 30 days
            samesite="lax",
            secure=False  # Set to True in production with HTTPS
        )
        return response

    except Exception as e:
        print(f"OAuth callback error: {e}")
        raise HTTPException(status_code=400, detail=f"Authentication failed: {str(e)}")


@app.get("/api/auth/me")
async def get_me(user: User = Depends(get_current_user)):
    """
    Get current authenticated user information.
    Requires valid JWT token in cookie.
    """
    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "picture_url": user.picture_url,
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "last_login": user.last_login.isoformat() if user.last_login else None
    }


@app.post("/api/auth/logout")
async def logout():
    """
    Logout user by clearing the JWT cookie.
    """
    response = JSONResponse({"message": "Logged out successfully"})
    response.delete_cookie("access_token")
    return response


@app.get("/api/auth/usage")
async def get_usage(user: Optional[User] = Depends(optional_user)):
    """
    Get usage statistics for current user or anonymous usage.
    Returns different data based on authentication status.
    """
    user_id = user.id if user else None
    return get_usage_stats(user_id)


@app.post("/api/anonymise", response_model=AnonymiseResponse, status_code=status.HTTP_200_OK)
async def anonymise(
    body: PipelineInput,
    user: Optional[User] = Depends(optional_user)
):
    """
    Anonymize text messages by detecting and redacting personally identifiable information (PII).
    Supports chat messages, SMS, emails, and any text containing personal data.
    Includes usage tracking and quota enforcement.

    Anonymous users: Limited to FREE_TIER_LIMIT requests
    Authenticated users: Unlimited requests (for now)

    Args:
        body: PipelineInput with rawText, blocklist, and sessionId
        user: Optional authenticated user from JWT cookie

    Returns:
        AnonymiseResponse with processed message and confidence scores

    Raises:
        HTTPException: 400 if rawText exceeds 500 character limit
        HTTPException: 401 if anonymous usage limit reached
        HTTPException: 403 if authenticated user quota exceeded
        HTTPException: 500 if processing fails
    """
    # Check usage limits
    if user:
        # Authenticated user - check user quota
        if not check_user_usage(user.id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Usage quota exceeded. Please upgrade your plan."
            )
    else:
        # Anonymous user - check global limit
        if not check_anonymous_usage():
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Free tier limit reached. Please login to continue."
            )

    # Validate text length
    if len(body.rawText) > 500:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="rawText exceeds 500 character limit"
        )

    try:
        # Run pipeline
        result = run_pipeline(body)

        # Increment usage counter AFTER successful processing
        if user:
            increment_user_usage(user.id)
        else:
            increment_anonymous_usage()

        # Return response (original field automatically excluded by Pydantic serializer)
        return AnonymiseResponse(result=result)

    except Exception as e:
        # Log error and return 500
        print(f"Pipeline error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Processing error: {str(e)}"
        )


def get_llm_client() -> OpenAICompatibleClient:
    return OpenAICompatibleClient()


@app.post("/api/chat", response_model=ChatResponse, status_code=status.HTTP_200_OK)
def private_chat(
    body: ChatRequest,
    user: Optional[User] = Depends(optional_user),
    llm: OpenAICompatibleClient = Depends(get_llm_client),
):
    """
    Anonymize the prompt, send only the anonymized text to the configured LLM,
    and return the answer with the original values restored.
    """
    if user:
        if not check_user_usage(user.id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Usage quota exceeded. Please upgrade your plan."
            )
    elif not check_anonymous_usage():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Free tier limit reached. Please login to continue."
        )

    try:
        result = run_private_chat(body.prompt, llm, blocklist=body.blocklist, strict=body.strict)
    except PrivacyRoutingError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"message": "Prompt not sent: anonymization needs review", "reasons": exc.reasons}
        )
    except VaultIntegrityError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Anonymization produced a placeholder that cannot be restored; prompt was not sent"
        )
    except LLMError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))

    if user:
        increment_user_usage(user.id)
    else:
        increment_anonymous_usage()

    return ChatResponse(
        answer=result.answer,
        anonymizedPrompt=result.anonymized_prompt,
        anonymizedAnswer=result.anonymized_answer,
        placeholdersSent=result.placeholders_sent,
        placeholdersRestored=result.placeholders_restored,
        unknownPlaceholders=result.unknown_placeholders,
        routing=result.routing,
        flags=result.flags,
        model=result.model,
    )


# Vercel serverless handler (ASGI adapter)
handler = Mangum(app)
