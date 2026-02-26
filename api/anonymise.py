"""
API Entry Point: FastAPI application with Vercel serverless support.
Provides /api/anonymise endpoint for WhatsApp message anonymization.
"""

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from mangum import Mangum
from lib.types import PipelineInput, AnonymiseResponse
from lib.pipeline.index import run_pipeline


# Initialize FastAPI app
app = FastAPI(
    title="WhatsApp Anonymization API",
    description="PII detection and redaction for WhatsApp messages",
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


@app.get("/")
async def root():
    """Health check endpoint."""
    return {
        "status": "ok",
        "service": "WhatsApp Anonymization API",
        "version": "1.0.0"
    }


@app.post("/api/anonymise", response_model=AnonymiseResponse, status_code=status.HTTP_200_OK)
async def anonymise(body: PipelineInput):
    """
    Anonymize WhatsApp message by detecting and redacting PII.

    Args:
        body: PipelineInput with rawText, blocklist, and sessionId

    Returns:
        AnonymiseResponse with processed message and confidence scores

    Raises:
        HTTPException: 400 if rawText exceeds 500 character limit
        HTTPException: 500 if processing fails
    """
    # Validate text length
    if len(body.rawText) > 500:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="rawText exceeds 500 character limit"
        )

    try:
        # Run pipeline
        result = run_pipeline(body)

        # Return response (original field automatically excluded by Pydantic serializer)
        return AnonymiseResponse(result=result)

    except Exception as e:
        # Log error and return 500
        print(f"Pipeline error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Processing error: {str(e)}"
        )


# Vercel serverless handler (ASGI adapter)
handler = Mangum(app)
