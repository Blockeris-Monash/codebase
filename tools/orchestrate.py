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
from fastapi import FastAPI, Query
from pydantic import BaseModel

# Import Milk's Extractor and Model
from extract_ai import AiExtractor
from qwen_model import qwen_model

# Import JJ's Deterministic Comparator
from comparator import ComparisonReport, compare_documents

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


# =====================================================================
# 2. Stage 2 Extraction: Hybrid (Pre-computed Cache + Live Qwen AI)
# =====================================================================

extractor = AiExtractor(qwen_model)

def load_saved_extract(email_id: str, role: str) -> Optional[Dict[str, Any]]:
    """Loads pre-extracted JSON from results/extracts/ if it exists."""
    extract_file = EXTRACTS_DIR / f"{email_id}_{role}.json"
    if extract_file.exists():
        try:
            data = json.loads(extract_file.read_text(encoding="utf-8"))
            # Unwrap the "fields" dictionary from DocumentExtract
            return data.get("fields", data)
        except Exception as e:
            log.warning("Failed to load cached extract for %s: %s", extract_file.name, e)
    return None

async def extract_document_fields(
    email_id: str,
    role: str,
    pairs: List[tuple[str, str]],
    force_live: bool = False,
) -> Dict[str, Any]:
    """Hybrid extractor: Uses Milk's saved results for instant speed,
    or falls back to live Qwen model with retry and hallucination checks.
    """
    # 1. Try cached extract if not forcing live AI
    if not force_live:
        cached = load_saved_extract(email_id, role)
        if cached:
            return cached

    # 2. Live extraction via Milk's AiExtractor (run in threadpool for async non-blocking concurrency)
    try:
        raw_fields = await asyncio.to_thread(extractor.extract_fields, email_id, pairs)
    except Exception as e:
        log.error("Live extraction failed for %s (%s): %s", email_id, role, e)
        raw_fields = None

    # 3. Graceful fallback if model returns None or fails
    if not raw_fields:
        return {field: {"present": False, "raw": None, "label_seen": None} for field in FIELD_NAMES}

    return raw_fields


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

@app.post("/extract-clean-compare", response_model=ComparisonReport)
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
    si_task = extract_document_fields(payload.email_id, "SI", payload.si_pairs, force_live=live)
    bl_task = extract_document_fields(payload.email_id, "BL", payload.bl_pairs, force_live=live)

    si_raw_fields, bl_raw_fields = await asyncio.gather(si_task, bl_task)

    # 2. Clean & normalize
    si_cleaned = apply_cleaner(si_raw_fields)
    bl_cleaned = apply_cleaner(bl_raw_fields)

    si_doc = {"email_id": payload.email_id, "fields": si_cleaned}
    bl_doc = {"email_id": payload.email_id, "fields": bl_cleaned}

    # 3. Deterministic comparison (JJ's Engine)
    report = compare_documents(si_doc, bl_doc)

    return report