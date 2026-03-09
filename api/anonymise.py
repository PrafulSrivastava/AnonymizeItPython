"""
API Entry Point: FastAPI application.
Provides /api/anonymise endpoint for text message anonymization and PII detection.
Supports chat messages, SMS, emails, and any text containing personal information.
Also provides /api/dlt/scan for batch scanning of DLT log files.
"""

# Load environment variables from .env file (must be first!)
from dotenv import load_dotenv
load_dotenv()

import os
import tempfile

from fastapi import FastAPI, HTTPException, UploadFile, File, Form, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

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


@app.post("/api/dlt/scan", status_code=status.HTTP_200_OK)
async def dlt_scan(
    file: UploadFile = File(..., description="DLT log file (.dlt binary or text export)"),
    blocklist: str = Form(default="", description="Comma-separated custom PII terms"),
    sample_size: int = Form(default=0, description="Max entries to scan (0 = unlimited)"),
):
    """
    Scan a DLT log file for residual PII and return a legal-grade anonymization report.

    Accepts binary .dlt files (AUTOSAR DLT storage-header format) and DLT Viewer text exports.
    Returns a JSON report with per-ECU/App PII statistics, routing breakdown, and legal risk level.

    Args:
        file: Uploaded DLT file
        blocklist: Comma-separated custom terms to treat as PII
        sample_size: Stop after this many entries (0 = whole file)

    Returns:
        JSON scan report with summary, PII stats, risk level, and flagged entries
    """
    # Validate filename extension loosely (binary magic is the real gate)
    filename = file.filename or "upload.dlt"
    allowed_suffixes = {".dlt", ".txt", ".log", ".csv"}
    ext = os.path.splitext(filename)[1].lower()
    if ext not in allowed_suffixes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file extension '{ext}'. Expected: {', '.join(sorted(allowed_suffixes))}",
        )

    # Write upload to a temp file so the parser can open it by path
    suffix = ext if ext else ".dlt"
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=suffix)
    try:
        contents = await file.read()
        if len(contents) == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Uploaded file is empty.",
            )
        # Enforce a 50 MB safety limit
        if len(contents) > 50 * 1024 * 1024:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="File exceeds the 50 MB limit.",
            )

        with os.fdopen(tmp_fd, "wb") as fh:
            fh.write(contents)
        tmp_fd = None  # fd is now closed via the context manager

        from lib.dlt.scanner  import DltScanner
        from lib.dlt.reporter import classify_risk, _RISK_RECOMMENDATIONS

        scanner = DltScanner(
            blocklist=blocklist,
            sample_size=sample_size,
            skip_control=True,
        )
        report = scanner.scan_file(tmp_path)

        if report.parsed_entries == 0:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="No scannable DLT entries found. Verify the file is a valid DLT export.",
            )

        risk = classify_risk(report)
        pii_rate    = report.entries_with_pii / max(report.parsed_entries, 1)
        review_rate = report.review_count     / max(report.parsed_entries, 1)

        return {
            "meta": {
                "filename":        filename,
                "scanned_at":      report.scanned_at,
                "blocklist_terms": report.blocklist_terms,
                "elapsed_s":       round(report.total_elapsed_s, 2),
            },
            "summary": {
                "total_entries":    report.total_entries,
                "parsed_entries":   report.parsed_entries,
                "skipped_entries":  report.skipped_entries,
                "pipeline_errors":  report.pipeline_errors,
                "pass_count":       report.pass_count,
                "pass_flagged":     report.pass_flagged_count,
                "review_count":     report.review_count,
                "entries_with_pii": report.entries_with_pii,
                "pii_rate":         round(pii_rate, 4),
                "review_rate":      round(review_rate, 4),
                "avg_confidence":   round(report.avg_confidence, 4),
                "min_confidence":   round(report.min_confidence, 4),
            },
            "pii_type_counts": report.pii_type_counts,
            "ecu_stats":        report.ecu_stats,
            "app_stats":        report.app_stats,
            "legal": {
                "risk_level":      risk,
                "recommendations": _RISK_RECOMMENDATIONS[risk],
            },
            "flagged_entries": [
                {
                    "index":     r.entry.index,
                    "ecu_id":    r.entry.ecu_id,
                    "app_id":    r.entry.app_id,
                    "ctx_id":    r.entry.ctx_id,
                    "log_level": r.entry.log_level,
                    "payload":   r.entry.payload,
                    "cleaned":   r.processed.cleanedText,
                    "routing":   r.routing,
                    "confidence": round(r.confidence, 4),
                    "pii_types": r.pii_types,
                    "tokens": [
                        {
                            "type":       t.type,
                            "value":      t.value,
                            "startIndex": t.startIndex,
                            "endIndex":   t.endIndex,
                            "confidence": round(t.confidence, 4),
                        }
                        for t in r.processed.tokens
                    ],
                }
                for r in report.flagged_results
            ],
        }

    except HTTPException:
        raise
    except Exception as exc:
        print(f"DLT scan error: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Scan failed: {str(exc)}",
        )
    finally:
        # Always clean up the temp file
        if tmp_fd is not None:
            try:
                os.close(tmp_fd)
            except OSError:
                pass
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
