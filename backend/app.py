"""Pipeline Orchestrator: Ingests document pairs, extracts via AI (Qwen/Cached),
cleans fields, and runs deterministic comparison.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

# Import Milk's Extractor and Model
from backend.classify import ClassificationFailed, ClassificationResult, EmailInput, classify_email
from backend.extract.ai import AiExtractor
from backend.extract.fallback import with_fallback
from backend.extract.gemini import api_key as gemini_key, gemini_model
from backend.extract.qwen import qwen_model

# Import JJ's Deterministic Comparator
from backend.compare.comparator import ComparisonResult, compare
from backend.contracts import DocumentRoleType, ParseStatusType
from backend.read.labels import detect_doc_type
from backend.translate import TooMuchText, TranslationFailed, translate_texts
from backend.read.documents import document_title, read_document


load_dotenv()
log = logging.getLogger(__name__)

app = FastAPI(title="Document Discrepancy Orchestrator")

from fastapi.middleware.cors import CORSMiddleware

# Enable CORS so Han's Vercel frontend can talk to Render
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins (or you can specify Han's Vercel domain later)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def health_check():
    """Lightweight endpoint for UptimeRobot and cloud health checkers."""
    return {"status": "ok"}


# Directory where Milk's pre-extracted results are stored
ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "data"
EXTRACTS_DIR = ROOT_DIR / "results" / "extracts"

FIELD_NAMES = [
    "shipper",
    "consignee",
    "notify_party",
    "port_of_loading",
    "port_of_discharge",
    "container_count",
    "gross_weight_kg",
]

SENTINEL = re.compile(r"^\s*$|^(n/?a|tba|tbc|-+)$|^_+\s*\w*$", re.I)

# =====================================================================
# 1. Input/Output Request Models
# =====================================================================

class PairedInput(BaseModel):
    email_id: str
    si_pairs: List[tuple[str, str]]
    bl_pairs: List[tuple[str, str]]
    # The reader saw the document's own header and knows whether the file
    # opened. Neither can be recovered from the pairs - a .txt SI leads with
    # Shipper, not with its title - and the comparator escalates any document
    # whose type or parse status is unknown, so the caller has to say.
    si_title: Optional[str]
    bl_title: Optional[str]
    si_parse_status: str = ParseStatusType.Ok
    bl_parse_status: str = ParseStatusType.Ok


# =====================================================================
# 2. Stage 3 Extraction: Hybrid (Pre-computed Cache + Live Qwen AI)
# =====================================================================

# Qwen first. If it fails or stalls, Gemini answers (with_fallback), but only when a Gemini key
# is set: without one, Qwen is used exactly as before, however slow it is. With a second
# provider behind, two tries are enough.
extractor = AiExtractor(with_fallback(qwen_model, gemini_model, enabled=lambda: bool(gemini_key())),
                        tries=2)

def load_saved_extract(email_id: str, role: str) -> Optional[Dict[str, Any]]:
    """The whole cached DocumentExtract, metadata included.

    Returning only `fields` drops parse_status and detected_doc_type, and the
    comparator escalates any document missing them - which was every document,
    so every email came back NEEDS_REVIEW/unreadable.
    """
    extract_file = EXTRACTS_DIR / f"{email_id}_{role}.json"
    if not extract_file.exists():
        return None

    try:
        return json.loads(extract_file.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        log.warning("Failed to load cached extract for %s: %s", extract_file.name, error)
        return None

ABSENT_FIELDS = {"present": False, "raw": None, "label_seen": None}


async def extract_live(
    email_id: str,
    role: str,
    pairs: List[tuple[str, str]],
    title: Optional[str],
    parse_status: str,
) -> Dict[str, Any]:
    """One document through Milk's AiExtractor, shaped as a DocumentExtract.

    Run in a threadpool so the SI and the BL extract concurrently.
    """
    try:
        raw_fields = await asyncio.to_thread(extractor.extract_fields, email_id, pairs)
    except Exception as error:  # third-party model client, any failure is one
        log.error("Live extraction failed for %s (%s): %s", email_id, role, error)
        raw_fields = None

    if not raw_fields:
        # A model that returned nothing is not evidence that the fields are
        # absent, so every field is marked missing and the comparator sends
        # the pair to a human rather than calling it a match.
        raw_fields = {field: dict(ABSENT_FIELDS) for field in FIELD_NAMES}

    return {
        "email_id": email_id,
        "declared_role": role,
        "detected_doc_type": detect_doc_type(title) if title else None,
        "parse_status": parse_status,
        "fields": raw_fields,
    }


def is_cache_current(cached: Dict[str, Any], title: Optional[str],
                     parse_status: str) -> bool:
    """Whether a saved extract describes the document the caller actually sent.

    The cache is keyed on (email_id, role) alone, so on its own it cannot tell
    "the same document again" from "a different document under the same id" -
    and it used to win either way, silently discarding the pairs, the title and
    the parse status the caller was asked to supply. A caller reporting a file
    that would not open, or a title that resolves to another document type, is
    describing something this record does not hold.
    """
    if parse_status != cached.get("parse_status"):
        return False
    if title is None:
        return True

    return detect_doc_type(title) == cached.get("detected_doc_type")


async def extract_document(
    email_id: str,
    role: str,
    pairs: List[tuple[str, str]],
    title: Optional[str],
    parse_status: str,
) -> Dict[str, Any]:
    """Cache first, model second. Milk's saved results answer instantly."""
    cached = load_saved_extract(email_id, role)
    if cached and is_cache_current(cached, title, parse_status):
        return cached

    return await extract_live(email_id, role, pairs, title, parse_status)


# =====================================================================
# 3. Normalization: contract 03 fields into comparable form (stage 4's front half)
# =====================================================================

def clean_entity(text: str) -> str:
    """Takes only the entity name before any address pipe ' | '."""
    first_segment = re.split(r"\s*\|\s*|\s{2,}", text)[0]
    return re.sub(r"\s+", " ", first_segment).upper().strip(" ,.;:")

def clean_port(text: str) -> str:
    first_segment = re.split(r"\s*\|\s*|\s{2,}", text)[0]
    # Remove UN/LOCODE in parentheses e.g. (MYPKG)
    text_no_locode = re.sub(r"\s*\(\s*[A-Z0-9]{5}\s*\)", "", first_segment, flags=re.I)
    return re.sub(r"\s+", " ", text_no_locode).upper().strip(" ,.;:")

def clean_containers(text: str) -> str:
    text = text.upper().strip()
    return re.sub(r"\s*X\s*", " x ", text)

def clean_weight(text: str) -> str:
    text_upper = text.upper()
    is_mt = "MT" in text_upper or "M/T" in text_upper
    numeric_str = re.sub(r"[^\d.]", "", text.replace(",", ""))
    if not numeric_str:
        return ""
    try:
        weight_val = float(numeric_str)
        if is_mt:
            weight_val *= 1000.0
        return str(weight_val)
    except ValueError:
        return text.strip()

def apply_cleaner(fields: Dict[str, Any]) -> Dict[str, Any]:
    cleaned: Dict[str, Any] = {}
    for key in FIELD_NAMES:
        field_data = fields.get(key, {"present": False, "raw": None})
        raw_text = field_data.get("raw")
        present = field_data.get("present", False)

        if not present or not raw_text or SENTINEL.match(str(raw_text).strip()):
            field_data["norm"] = None
        else:
            raw_str = str(raw_text).strip()
            if key in ["shipper", "consignee", "notify_party"]:
                field_data["norm"] = clean_entity(raw_str)
            elif key in ["port_of_loading", "port_of_discharge"]:
                field_data["norm"] = clean_port(raw_str)
            elif key == "container_count":
                field_data["norm"] = clean_containers(raw_str)
            elif key == "gross_weight_kg":
                field_data["norm"] = clean_weight(raw_str)
            else:
                field_data["norm"] = raw_str

        cleaned[key] = field_data
    return cleaned


# =====================================================================
# 4. FastAPI Endpoint: Extract -> Clean -> Compare
# =====================================================================

@app.post("/extract-clean-compare", response_model=ComparisonResult)
async def run_pipeline(
    payload: PairedInput,
    live: bool = Query(
        False, description="Set to true to force live Qwen AI call instead of loading saved extracts"
    ),
):
    """Orchestrates the full flow:
    1. Extracts SI & BL concurrently using Milk's AiExtractor (Hybrid mode).
    2. Cleans & normalizes values into standard comparable formats.
    3. Evaluates discrepancies using JJ's deterministic engine.
    """
    # 1. Concurrently extract SI and BL
    extract = extract_live if live else extract_document
    si_extract, bl_extract = await asyncio.gather(
        extract(payload.email_id, DocumentRoleType.Si, payload.si_pairs,
                payload.si_title, payload.si_parse_status),
        extract(payload.email_id, DocumentRoleType.Bl, payload.bl_pairs,
                payload.bl_title, payload.bl_parse_status),
    )

    # 2. Clean & normalize, keeping the metadata the comparator prechecks on
    # A document that was never found is None, not one that failed to parse.
    # The comparator's first precheck is what turns that into
    # missing_attachment rather than the misleading unreadable.
    si_doc = None if payload.si_parse_status == ParseStatusType.Missing else {
        **si_extract, "fields": apply_cleaner(si_extract["fields"])}
    bl_doc = None if payload.bl_parse_status == ParseStatusType.Missing else {
        **bl_extract, "fields": apply_cleaner(bl_extract["fields"])}

    # 3. Deterministic comparison (JJ's Engine)
    report = compare(payload.email_id, si_doc, bl_doc)

    return report


# --- classification (Hanif's, lifted out of its own server) -------------

# --- translation for the UI's Translate button --------------------------

class TranslateRequest(BaseModel):
    # A free-text target is interpolated straight into the prompt, so a caller
    # could send instructions dressed as a language. The UI only ever offers
    # these three.
    target: Literal["English", "Malay", "Chinese"]
    texts: Dict[str, str]


class TranslateResponse(BaseModel):
    texts: Dict[str, str]


@app.post("/translate", response_model=TranslateResponse)
async def translate(request: TranslateRequest) -> TranslateResponse:
    """The email and its documents translated into one language."""
    try:
        return TranslateResponse(texts=await asyncio.to_thread(translate_texts, request.texts, request.target))
    except TooMuchText as error:
        raise HTTPException(status_code=413, detail=str(error)) from error
    except (TranslationFailed, RuntimeError) as error:
        raise HTTPException(status_code=502, detail=str(error)) from error


@app.post("/classify", response_model=ClassificationResult)
async def classify(email: EmailInput) -> ClassificationResult:
    """One email in, one ClassificationResult out. Contract 02."""
    try:
        return await classify_email(email)
    except ClassificationFailed as error:
        raise HTTPException(status_code=502, detail=str(error)) from error

# =====================================================================
# 5. Routing Helpers: Attachment Resolution
# =====================================================================

def resolve_attachment_path(att_path_str: str) -> Optional[Path]:
    """Finds the attachment file in data/attachments/ or local paths."""
    p = Path(att_path_str)
    if p.is_absolute() and p.exists():
        return p
    # Look inside data/attachments/<filename>
    direct = DATA_DIR / "attachments" / p.name
    if direct.exists():
        return direct
    # Look inside data/<relative_path>
    relative = DATA_DIR / att_path_str
    if relative.exists():
        return relative
    return None


def read_paired_attachments(email: EmailInput) -> PairedInput:
    """Locates SI and BL attachments, reads label/value pairs, and records parse status."""
    si_path_str = next(
        (a for a in email.attachments if f"_{DocumentRoleType.Si}." in a or a.upper().endswith("SI")),
        None,
    )
    bl_path_str = next(
        (a for a in email.attachments if f"_{DocumentRoleType.Bl}." in a or a.upper().endswith("BL")),
        None,
    )

    si_file = resolve_attachment_path(si_path_str) if si_path_str else None
    bl_file = resolve_attachment_path(bl_path_str) if bl_path_str else None

    # Read SI
    if si_file and si_file.exists():
        si_status, si_pairs = read_document(si_file)
        si_title = document_title(si_file)
    else:
        si_status, si_pairs, si_title = ParseStatusType.Missing, [], None

    # Read BL
    if bl_file and bl_file.exists():
        bl_status, bl_pairs = read_document(bl_file)
        bl_title = document_title(bl_file)
    else:
        bl_status, bl_pairs, bl_title = ParseStatusType.Missing, [], None

    return PairedInput(
        email_id=email.email_id,
        si_pairs=si_pairs,
        bl_pairs=bl_pairs,
        si_title=si_title,
        bl_title=bl_title,
        si_parse_status=si_status,
        bl_parse_status=bl_status,
    )


# =====================================================================
# 6. Master Route: Classify -> Route (Compare or Pass-Through)
# =====================================================================

@app.post("/process-email")
async def process_email(
    email: EmailInput,
    live: bool = Query(
        False, description="Set to true to force live Qwen AI calls instead of cached extracts"
    ),
) -> Dict[str, Any]:
    """1-Click End-to-End Entrypoint:
    1. Classifies email category.
    2. Routes BL_COMPARISON to document extraction and comparison.
    3. Passes through non-comparison emails with null ComparisonResult.
    """
    # 1. Classify the email
    classification = await classify(email)

    # 2. Build standard EmailRecord structure
    sender_domain = email.from_email.split("@")[-1] if "@" in email.from_email else ""
    email_record = {
        "email_id": email.email_id,
        "from": email.from_email,
        "sender_domain": sender_domain,
        "subject": email.subject,
        "body": email.body,
        "attachments": email.attachments,
    }

    # 3. Non-comparison branch (SI_REQUEST, INVOICE_QUERY, GENERAL, SPAM)
    if classification.category != "BL_COMPARISON":
        return {
            "email_id": email.email_id,
            "EmailRecord": email_record,
            "ClassificationResult": classification.model_dump(),
            "ComparisonResult": None,
            "SubmissionEntry": {
                "category": classification.category,
                "status": "OK",
                "review_reason": None,
                "has_defect": False,
                "defect_fields": [],
            },
        }

    # 4. BL_COMPARISON branch: resolve attachments & run comparison pipeline
    paired_input = read_paired_attachments(email)
    comparison = await run_pipeline(paired_input, live=live)

    comparison_dict = comparison.model_dump() if hasattr(comparison, "model_dump") else comparison

    return {
        "email_id": email.email_id,
        "EmailRecord": email_record,
        "ClassificationResult": classification.model_dump(),
        "ComparisonResult": comparison_dict,
        "SubmissionEntry": {
            "category": classification.category,
            "status": comparison_dict.get("status", "OK"),
            "review_reason": comparison_dict.get("review_reason"),
            "has_defect": bool(comparison_dict.get("defect_fields")),
            "defect_fields": comparison_dict.get("defect_fields", []),
        },
    }