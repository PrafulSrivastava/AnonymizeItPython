"""
API Entry Point: FastAPI application.
Provides /api/anonymise endpoint for text message anonymization and PII detection.
Supports chat messages, SMS, emails, and any text containing personal information.
"""

# Load environment variables from .env file (must be first!)
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import os

from lib.types import PipelineInput, AnonymiseResponse
from lib.pipeline.index import run_pipeline


# Initialize FastAPI app
app = FastAPI(
    title="Text Anonymization API",
    description="Advanced PII detection and redaction for chat messages, SMS, emails, and text data using NER and ML",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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


@app.post("/api/anonymise", response_model=AnonymiseResponse, status_code=status.HTTP_200_OK)
async def anonymise(body: PipelineInput):
    """
    Anonymize text messages by detecting and redacting personally identifiable information (PII).
    Supports chat messages, SMS, emails, and any text containing personal data.

    Args:
        body: PipelineInput with rawText, blocklist, and sessionId

    Returns:
        AnonymiseResponse with processed message and confidence scores

    Raises:
        HTTPException: 400 if rawText exceeds 500 character limit
        HTTPException: 500 if processing fails
    """
    try:
        result = run_pipeline(body)
        return AnonymiseResponse(result=result)
    except Exception as e:
        print(f"Pipeline error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Processing error: {str(e)}"
        )
