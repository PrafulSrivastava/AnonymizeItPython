"""
Pydantic models for the anonymization pipeline.
Defines the API contract and internal data structures.
"""

from typing import List, Optional, Literal
from pydantic import BaseModel, Field, field_serializer


# Token types
TokenType = Literal[
    "PHONE", "EMAIL", "URL", "HANDLE", "AGE", "DOB",
    "PERSON", "ORG", "LOCATION", "IBAN", "BLOCKLIST", "SENDER"
]

# Routing decisions
RoutingDecision = Literal["pass", "pass_flagged", "review"]

MAX_WORKFLOW_CHARS = 8000


class PipelineInput(BaseModel):
    """Request body for anonymization endpoint."""
    rawText: str = Field(..., max_length=MAX_WORKFLOW_CHARS, description="Raw text to anonymize")
    blocklist: str = Field(default="", description="Comma-separated list of terms to redact")
    sessionId: str = Field(..., description="Session identifier for tracking")


class RedactionToken(BaseModel):
    """Individual PII replacement token."""
    type: TokenType = Field(..., description="Type of PII detected")
    value: str = Field(..., description="Replacement token (e.g., [PHONE_01])")
    original: str = Field(..., description="Original PII text (server-side only, never serialized)")
    startIndex: int = Field(..., description="Start position in original text")
    endIndex: int = Field(..., description="End position in original text")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Detection confidence score")
    lowConfidence: bool = Field(default=False, description="Flag for low confidence detections")

    @field_serializer('original')
    def exclude_original(self, value: str) -> None:
        """Never serialize the 'original' field to API responses."""
        return None


class ConfidenceSignals(BaseModel):
    """Breakdown of confidence scoring components."""
    regexCoverage: float = Field(..., ge=0.0, le=1.0, description="Regex pattern match coverage")
    nerConfidence: float = Field(..., ge=0.0, le=1.0, description="Average NER confidence score")
    quasiIdentifierCount: int = Field(..., ge=0, description="Count of quasi-identifiers detected")
    residualTokenDensity: float = Field(..., ge=0.0, le=1.0, description="Density of non-redacted tokens")


class ConfidenceScore(BaseModel):
    """Overall confidence score with routing decision."""
    overall: float = Field(..., ge=0.0, le=1.0, description="Weighted overall confidence score")
    routing: RoutingDecision = Field(..., description="Routing decision based on threshold")
    signals: ConfidenceSignals = Field(..., description="Component signal breakdown")
    failureReasons: List[str] = Field(default_factory=list, description="Human-readable failure reasons")


class ProcessedMessage(BaseModel):
    """Complete result object after pipeline processing."""
    messageId: str = Field(..., description="SHA-256 hash of message + sessionId")
    cleanedText: str = Field(..., description="Anonymized message text with tokens")
    tokens: List[RedactionToken] = Field(default_factory=list, description="List of all redaction tokens")
    confidence: ConfidenceScore = Field(..., description="Confidence scoring and routing")
    flags: dict = Field(
        default_factory=dict,
        description="Additional flags (quasi_identifier_risk, low_signal, etc.)"
    )
    metadata: dict = Field(
        default_factory=dict,
        description="Processing metadata (timestamp, pipeline version, etc.)"
    )


class AnonymiseResponse(BaseModel):
    """Response wrapper for the API endpoint."""
    result: ProcessedMessage = Field(..., description="Processed message result")

    model_config = {
        "json_schema_extra": {
            "example": {
                "result": {
                    "messageId": "abc123...",
                    "cleanedText": "[SENDER] [PERSON_01]: Contact me at [EMAIL_01]",
                    "tokens": [
                        {
                            "type": "SENDER",
                            "value": "[SENDER]",
                            "startIndex": 0,
                            "endIndex": 8,
                            "confidence": 1.0,
                            "lowConfidence": False
                        }
                    ],
                    "confidence": {
                        "overall": 0.92,
                        "routing": "pass",
                        "signals": {
                            "regexCoverage": 0.95,
                            "nerConfidence": 0.88,
                            "quasiIdentifierCount": 0,
                            "residualTokenDensity": 0.75
                        },
                        "failureReasons": []
                    },
                    "flags": {
                        "quasi_identifier_risk": False,
                        "low_signal": False
                    },
                    "metadata": {}
                }
            }
        }
    }


class ChatRequest(BaseModel):
    """Request body for the private chat workflow."""
    prompt: str = Field(..., min_length=1, max_length=MAX_WORKFLOW_CHARS, description="Prompt that may contain PII")
    blocklist: str = Field(default="", description="Comma-separated list of extra terms to redact")
    strict: bool = Field(default=False, description="Refuse to call the LLM when routing is 'review'")


class ChatResponse(BaseModel):
    """Re-enriched LLM answer plus what was actually sent to the model."""
    answer: str = Field(..., description="LLM answer with original values restored")
    anonymizedPrompt: str = Field(..., description="Exact prompt text sent to the LLM")
    anonymizedAnswer: str = Field(..., description="LLM answer before re-enrichment")
    placeholdersSent: List[str] = Field(default_factory=list)
    placeholdersRestored: List[str] = Field(default_factory=list)
    unknownPlaceholders: List[str] = Field(default_factory=list, description="Placeholders the LLM emitted that were never sent")
    routing: RoutingDecision
    flags: dict = Field(default_factory=dict)
    model: str
