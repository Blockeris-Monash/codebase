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
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

# Import Milk's Extractor and Model
from backend.classify import ClassificationFailed, ClassificationResult, EmailInput, classify_email
from backend.extract.ai import AiExtractor
from backend.extract.qwen import qwen_model

# Import JJ's Deterministic Comparator
from backend.compare.comparator import ComparisonResult, compare
from backend.contracts import DocumentRoleType, ParseStatusType
from backend.read.labels import detect_doc_type

load_dotenv()
log = logging.getLogger(__name__)

app = FastAPI(title="Document Discrepancy Orchestrator")

# Directory where Milk's pre-extracted results are stored
ROOT_DIR = Path(__file__).resolve().parents[1]
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
# 2. Stage 2 Extraction: Hybrid (Pre-computed Cache + Live Qwen AI)
# =====================================================================

extractor = AiExtractor(qwen_model)

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


async def extract_document(
    email_id: str,
    role: str,
    pairs: List[tuple[str, str]],
    title: Optional[str],
    parse_status: str,
) -> Dict[str, Any]:
    """Cache first, model second. Milk's saved results answer instantly."""
    cached = load_saved_extract(email_id, role)
    if cached:
        return cached

    return await extract_live(email_id, role, pairs, title, parse_status)


# =====================================================================
# 3. Stage 3 Normalization: Formatting for JJ's Comparator
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
    si_doc = {**si_extract, "fields": apply_cleaner(si_extract["fields"])}
    bl_doc = {**bl_extract, "fields": apply_cleaner(bl_extract["fields"])}

    # 3. Deterministic comparison (JJ's Engine)
    report = compare(payload.email_id, si_doc, bl_doc)

    return report


# --- classification (Hanif's, lifted out of its own server) -------------

@app.post("/classify", response_model=ClassificationResult)
async def classify(email: EmailInput) -> ClassificationResult:
    """One email in, one ClassificationResult out. Contract 02."""
    try:
        return await classify_email(email)
    except ClassificationFailed as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
