import logging
import os
import sys
from pathlib import Path
from typing import Literal, List
from pydantic import BaseModel, Field
from dotenv import load_dotenv

# Use JJ's official SDK approach
from google import genai
from google.genai import types

load_dotenv()
log = logging.getLogger(__name__)


class ClassificationFailed(RuntimeError):
    """The model never returned a usable classification."""

# Initialize async client
_client: genai.Client | None = None


def get_client() -> genai.Client:
    """Built on first use, not at import. Constructing it at module level
    means the whole app fails to import without a key - which breaks the
    tests, a clean clone, and any build step that only needs to load the
    module."""
    global _client
    if _client is None:
        key = os.getenv("GOOGLE_API_KEY")
        if not key:
            raise ClassificationFailed("GOOGLE_API_KEY is not set")
        _client = genai.Client(api_key=key)

    return _client

# ==========================================
# 1. Input/Output Contracts
# ==========================================
class EmailInput(BaseModel):
    email_id: str
    from_email: str = Field(..., alias="from") 
    subject: str
    body: str
    attachments: List[str] = []

class ClassificationResult(BaseModel):
    email_id: str
    category: str
    decided_by: str
    confidence: float
    evidence: str

# ==========================================
# 2. JJ's Strict LLM Schema
# ==========================================
class GeminiClassificationSchema(BaseModel):
    category: Literal[
        "BL_COMPARISON",
        "SI_REQUEST",
        "INVOICE_QUERY",
        "GENERAL",
        "SPAM",
    ] = Field(..., description="The single operational category matching the email.")
    
    # JJ's fixed confidence tiers
    confidence_tier: Literal["1.0", "0.85", "0.65", "0.50"] = Field(
        ...,
        description=(
            "Select confidence level based on these criteria:\n"
            "- '1.0': Explicit, unambiguous intent matching operational definition.\n"
            "- '0.85': Clear intent with strong context, but informal phrasing.\n"
            "- '0.65': Multiple topics/signals present; one is primary.\n"
            "- '0.50': Vague or conflicting signals (best guess)."
        ),
    )
    evidence: str = Field(
        ...,
        description="Verbatim excerpt or concise phrase from the email justifying the category.",
    )

# ==========================================
# 3. Merged Async Route
# ==========================================
async def classify_email(email: EmailInput):
    # JJ's prompt logic + Your FastAPI context
    prompt = f"""
    You are an AI shipping operations email triage classifier.
    Classify this email into EXACTLY ONE category.
    
    Categories:
    - BL_COMPARISON: Asking to check, verify, confirm, or compare draft Bill of Lading (BL) against Shipping Instruction (SI).
    - SI_REQUEST: Requesting to create or submit a new Shipping Instruction.
    - INVOICE_QUERY: Inquiries about ocean invoices, D&D / detention fees, freight billing.
    - GENERAL: Internal operational updates, vessel berthing notices, daily schedules.
    - SPAM: Phishing, scams, promotions, or external spam.

    Email Content:
    - Email ID: {email.email_id}
    - From: {email.from_email}
    - Subject: {email.subject}
    - Body:
    {email.body[:1500]} 
    """

    try:
        # Use the SDK's async method (generate_content_async)
        response = await get_client().aio.models.generate_content(
            model="gemini-3.5-flash-lite", # Or gemini-3.6-flash depending on your latency needs
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=GeminiClassificationSchema,
                temperature=0.0, 
            ),
        )
        
        # Parse SDK response using JJ's schema
        parsed = GeminiClassificationSchema.model_validate_json(response.text)
        
        # Apply your post-processing safety nets
        return ClassificationResult(
            email_id=email.email_id, # Hardcoded from input
            category=parsed.category,
            decided_by="llm",        # Hardcoded from input
            confidence=float(parsed.confidence_tier),
            evidence=parsed.evidence
        )
        
    except Exception as error:
        # The caller decides how to surface this; classify.py stays transport
        # agnostic now that the route lives in app.py.
        log.exception("classification failed for %s", email.email_id)
        raise ClassificationFailed(str(error)) from error