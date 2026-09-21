"""Lane C - Stage 4: Document Comparison Engine.

Strictly compliant with ComparisonResult JSON Schema (Draft 2020-12).
No LLM/API dependencies: 100% deterministic local Python.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path as _Path
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

sys.path.insert(0, str(_Path(__file__).resolve().parents[1] / "tools"))
from normalise import normalise  # noqa: E402

# Distinguishes "no norm key at all" from "norm supplied as None".
_MISSING = object()

# The 7 canonical fields required by the contract
CANONICAL_FIELDS = [
    "shipper",
    "consignee",
    "notify_party",
    "port_of_loading",
    "port_of_discharge",
    "container_count",
    "gross_weight_kg",
]

FieldType = Literal[
    "shipper",
    "consignee",
    "notify_party",
    "port_of_loading",
    "port_of_discharge",
    "container_count",
    "gross_weight_kg",
]

VerdictType = Literal["match", "mismatch", "missing"]
StatusType = Literal["OK", "MISMATCH", "NEEDS_REVIEW"]
ReviewReasonType = Literal[
    "wrong_doc_type", "missing_attachment", "unreadable", "missing_value"
]


# =====================================================================
# Pydantic Output Contract (ComparisonResult)
# =====================================================================

class Row(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: FieldType
    si_raw: Optional[str] = None
    bl_raw: Optional[str] = None
    si_norm: Optional[str] = None
    bl_norm: Optional[str] = None
    verdict: VerdictType


class ComparisonResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email_id: str = Field(..., pattern=r"^email_[0-9]{3}$")
    status: StatusType
    review_reason: Optional[ReviewReasonType] = None
    rows: List[Row]
    defect_fields: List[FieldType]
    evidence: str


# =====================================================================
# Deterministic Normalization & Comparison Helpers
# =====================================================================

LOCODE_DECOY = re.compile(r"\s*\(([A-Z]{5})\)\s*|\b[A-Z]{2}[A-Z0-9]{3}\b", re.I)


def extract_meaningful_tokens(val: str | None) -> set[str]:
    """Strips planted LOCODE decoys and returns uppercase alphanumeric tokens."""
    if not val:
        return set()
    cleaned = LOCODE_DECOY.sub("", val.upper())
    return set(re.findall(r"\b[A-Z0-9]{2,}\b", cleaned))


def compare_single_field(
    field: str, si_norm: Optional[str], bl_norm: Optional[str]
) -> VerdictType:
    """Computes exact schema verdict: 'match', 'mismatch', or 'missing'."""
    # A field with a missing or blank normalized value on either side is missing
    if si_norm is None or bl_norm is None:
        return "missing"
    if str(si_norm).strip() == "" or str(bl_norm).strip() == "":
        return "missing"

    s_norm = str(si_norm).strip().upper()
    b_norm = str(bl_norm).strip().upper()

    # Fast path: exact string identity
    if s_norm == b_norm:
        return "match"

    # 1. Weights: numerical comparison with float tolerance
    if field == "gross_weight_kg":
        try:
            val_si = float(s_norm.replace(",", ""))
            val_bl = float(b_norm.replace(",", ""))
            return "match" if abs(val_si - val_bl) <= 0.1 else "mismatch"
        except (ValueError, TypeError):
            return "mismatch"

    # 2. Container Count: leading integer extraction
    if field == "container_count":
        match_si = re.search(r"\d+", s_norm)
        match_bl = re.search(r"\d+", b_norm)
        c_si = match_si.group(0) if match_si else s_norm
        c_bl = match_bl.group(0) if match_bl else b_norm
        return "match" if c_si == c_bl else "mismatch"

    # 3. Ports: token-set subset match (handles country additions/inversions)
    if field in {"port_of_loading", "port_of_discharge"}:
        si_tokens = extract_meaningful_tokens(s_norm)
        bl_tokens = extract_meaningful_tokens(b_norm)
        if si_tokens and bl_tokens and (
            si_tokens == bl_tokens
            or si_tokens.issubset(bl_tokens)
            or bl_tokens.issubset(si_tokens)
        ):
            return "match"

    return "mismatch"


# =====================================================================
# Main Comparison Runner
# =====================================================================

def compare(
    email_id: str,
    si_doc: Optional[Dict[str, Any]],
    bl_doc: Optional[Dict[str, Any]],
) -> ComparisonResult:
    """Consumes SI & BL extractions and returns the validated ComparisonResult."""
    # Pre-check 1: Missing attachment
    if si_doc is None or bl_doc is None:
        missing_doc = "SI" if si_doc is None else "BL"
        return ComparisonResult(
            email_id=email_id,
            status="NEEDS_REVIEW",
            review_reason="missing_attachment",
            rows=[],
            defect_fields=[],
            evidence=f"Missing attachment: {missing_doc} document was not provided.",
        )

    # Pre-check 2: Unreadable. This comes before the document-type check
    # because a file that would not open has no title to read, so its type
    # is unknown rather than wrong. Emails 511-515 are exactly this case.
    if si_doc.get("parse_status") != "ok" or bl_doc.get("parse_status") != "ok":
        return ComparisonResult(
            email_id=email_id,
            status="NEEDS_REVIEW",
            review_reason="unreadable",
            rows=[],
            defect_fields=[],
            evidence="Unreadable document: extraction stage could not parse document contents.",
        )

    # Pre-check 3: Wrong document type
    if si_doc.get("detected_doc_type") != "SI" or bl_doc.get("detected_doc_type") != "BL":
        return ComparisonResult(
            email_id=email_id,
            status="NEEDS_REVIEW",
            review_reason="wrong_doc_type",
            rows=[],
            defect_fields=[],
            evidence="Document type error: attached files could not be confirmed as SI and BL.",
        )


    # Build the 7 comparison rows
    rows: List[Row] = []
    defect_fields: List[FieldType] = []
    missing_fields: List[str] = []

    si_fields = si_doc.get("fields", {})
    bl_fields = bl_doc.get("fields", {})

    for field_name in CANONICAL_FIELDS:
        si_item = si_fields.get(field_name, {})
        bl_item = bl_fields.get(field_name, {})

        si_raw = si_item.get("raw")
        bl_raw = bl_item.get("raw")
        # Contract 03 supplies `raw` only. Extraction leaves values exactly as
        # written so the review screen can show source evidence; normalising
        # is this stage's job. Fall back to a supplied `norm` if a caller
        # happens to pre-normalise.
        si_norm = si_item.get("norm", _MISSING)
        bl_norm = bl_item.get("norm", _MISSING)
        if si_norm is _MISSING:
            si_norm = normalise(field_name, si_raw)
        if bl_norm is _MISSING:
            bl_norm = normalise(field_name, bl_raw)

        verdict = compare_single_field(field_name, si_norm, bl_norm)

        if verdict == "mismatch":
            defect_fields.append(field_name)  # type: ignore
        elif verdict == "missing":
            missing_fields.append(field_name)

        rows.append(
            Row(
                field=field_name,  # type: ignore
                si_raw=str(si_raw) if si_raw is not None else None,
                bl_raw=str(bl_raw) if bl_raw is not None else None,
                si_norm=str(si_norm) if si_norm is not None else None,
                bl_norm=str(bl_norm) if bl_norm is not None else None,
                verdict=verdict,
            )
        )

    # Priority Rule 1: Any missing values trigger NEEDS_REVIEW
    if missing_fields:
        return ComparisonResult(
            email_id=email_id,
            status="NEEDS_REVIEW",
            review_reason="missing_value",
            rows=rows,
            defect_fields=[],  # Schema specifies defect_fields empty unless status == MISMATCH
            evidence=f"Missing value detected in fields: {', '.join(missing_fields)}.",
        )

    # Priority Rule 2: Hard discrepancies trigger MISMATCH
    if defect_fields:
        return ComparisonResult(
            email_id=email_id,
            status="MISMATCH",
            review_reason=None,  # Must be null if status != NEEDS_REVIEW
            rows=rows,
            defect_fields=defect_fields,
            evidence=f"Discrepancies found in {len(defect_fields)} field(s): {', '.join(defect_fields)}.",
        )

    # Priority Rule 3: Complete clean match
    return ComparisonResult(
        email_id=email_id,
        status="OK",
        review_reason=None,
        rows=rows,
        defect_fields=[],
        evidence="All 7 fields match between SI and BL.",
    )


# =====================================================================
# Verification Unit Tests for email_517 (NEEDS_REVIEW Case)
# =====================================================================

if __name__ == "__main__":
    # Extracted and normalized from email_517_SI.txt
    si_input_517 = {
        "email_id": "email_517",
        "detected_doc_type": "SI",
        "parse_status": "ok",
        "fields": {
            "shipper": {
                "raw": "APRIL FAR EAST (M) SDN BHD",
                "norm": "APRIL FAR EAST (M) SDN BHD",
            },
            "consignee": {
                "raw": "BALL & DOGGETT AUSTRALIA PTY LTD",
                "norm": "BALL & DOGGETT AUSTRALIA PTY LTD",
            },
            "notify_party": {
                "raw": "BALL & DOGGETT AUSTRALIA PTY LTD",
                "norm": "BALL & DOGGETT AUSTRALIA PTY LTD",
            },
            "port_of_loading": {
                "raw": "____MT",
                "norm": None,  # Blank placeholder normalizes to null
            },
            "port_of_discharge": {
                "raw": "TBA",
                "norm": None,  # TBA normalizes to null
            },
            "container_count": {
                "raw": "15 x 20'GP",
                "norm": "15 X 20'GP",
            },
            "gross_weight_kg": {
                "raw": "340,770 KG",
                "norm": "340770",
            },
        },
    }

    # Extracted and normalized from email_517_BL.txt
    bl_input_517 = {
        "email_id": "email_517",
        "detected_doc_type": "BL",
        "parse_status": "ok",
        "fields": {
            "shipper": {
                "raw": "APRIL FAR EAST (M) SDN BHD\n  TOWER 2, AVENUE 5, LEVEL 6; BANGSAR SOUTH CITY, NO. 8 JALAN KERINCHI; 59200 KUALA LUMPUR, MALAYSIA",
                "norm": "APRIL FAR EAST (M) SDN BHD",
            },
            "consignee": {
                "raw": "BALL & DOGGETT AUSTRALIA PTY LTD\n  43-45 METROPOLITAN ROAD; ENFIELD NSW 2136, AUSTRALIA",
                "norm": "BALL & DOGGETT AUSTRALIA PTY LTD",
            },
            "notify_party": {
                "raw": "BALL & DOGGETT AUSTRALIA PTY LTD",
                "norm": "BALL & DOGGETT AUSTRALIA PTY LTD",
            },
            "port_of_loading": {
                "raw": "SINGAPORE (SGSIN)",
                "norm": "SINGAPORE",
            },
            "port_of_discharge": {
                "raw": "CALLAO, PERU (PECLL)",
                "norm": "CALLAO, PERU",
            },
            "container_count": {
                "raw": "15 x 20'GP",
                "norm": "15 X 20'GP",
            },
            "gross_weight_kg": {
                "raw": "340,770 KG",
                "norm": "340770",
            },
        },
    }

    result = compare("email_517", si_input_517, bl_input_517)
    print("Schema Output for email_517:")
    print(json.dumps(result.model_dump(), indent=2))