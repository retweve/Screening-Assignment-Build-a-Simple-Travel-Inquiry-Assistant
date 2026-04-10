"""
app.py - FastAPI application for the WanderFlow Travel Inquiry Assistant.

Run with:
    uvicorn app:app --reload
"""

import logging
import sys

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, field_validator

from config import settings
from parser import process_inquiry

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

logging.basicConfig(
    stream=sys.stdout,
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(
    title="WanderFlow Travel Inquiry Assistant",
    description=(
        "Accepts a raw customer travel inquiry and returns structured JSON "
        "with extracted fields and an AI-generated reply."
    ),
    version="1.0.0",
)


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------

class InquiryRequest(BaseModel):
    message: str

    @field_validator("message")
    @classmethod
    def message_must_not_be_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("message must not be empty")
        if len(v) > 2000:
            raise ValueError("message must be 2000 characters or fewer")
        return v


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/", tags=["Health"])
async def health_check():
    """Simple health-check endpoint."""
    return {"status": "ok", "service": "WanderFlow Travel Inquiry Assistant"}


@app.post("/inquire", tags=["Inquiry"])
async def inquire(request: InquiryRequest):
    """
    Process a travel inquiry message and return structured JSON.

    - Extracts or infers trip details (destination, duration, budget, etc.)
    - Identifies missing important fields
    - Generates a short, professional customer-facing reply
    """
    logger.info("Received inquiry: %s", request.message[:80])
    try:
        result = await process_inquiry(request.message)
    except Exception as exc:
        logger.exception("Unexpected error processing inquiry")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    logger.info(
        "Processed inquiry — intent=%s reply_type=%s missing=%s",
        result.get("intent"),
        result.get("reply_type"),
        result.get("missing_fields"),
    )
    return JSONResponse(content=result)
