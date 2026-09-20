"""Lane C - Step 4: Full Document Comparison Engine.

Consumes the cleaned JSON extraction documents (from Step 3 / Hanif)
and outputs a structured comparison report compliant with Contract 5.
"""
from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from google import genai
from google.genai import types

# Initialize Gemini Client for semantic fallbacks
api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=api_key) if api_key else genai.Client()


# =====================================================================
# 1. Output Contract (Contract 5: ComparisonReport)
# =====================================================================

class Discrepancy(BaseModel):
    field: str = Field(..., description="Target field evaluated.")
    status: str = Field(..., description="'Match', 'Mismatch', or 'Missing'")
    si_raw: Optional[str] = Field(None, description="Raw value from Shipping Instruction.")
    bl_raw: Optional[str] = Field(None, description="Raw value from Bill of Lading.")
    si_norm: Optional[str] = Field(None, description="Cleaned value from SI.")
    bl_norm: Optional[str] = Field(None, description="Cleaned value from BL.")
    verdict: str = Field(..., description="'Match', 'Mismatch', or 'Missing'")
    notes: Optional[str] = Field(None, description="Details or reasoning behind the verdict.")


class ComparisonReport(BaseModel):
    email_id: str
    match_status: str = Field(..., description="'CLEAN_MATCH' or 'DISCREPANCIES_FOUND'")
    total_fields_checked: int
    discrepancies_count: int
    rows: List[Discrepancy]


# =====================================================================
# 2. Semantic Fallback (Gemini 3.6 Flash)
# =====================================================================

def llm_verify_semantic_match(field_name: str, si_val: str, bl_val: str) -> bool:
    """Evaluates whether two diverging strings describe the same real-world entity/port."""
    prompt = f"""
    You are an expert shipping document auditor comparing a Shipping Instruction (SI) and a Bill of Lading (BL).
    Determine if these two values refer to the EXACT SAME physical entity, port, or facility, despite differences in word order, punctuation, or formatting.

    CRITICAL RULES:
    - 5-letter UN/LOCODEs in brackets (e.g. (MYPKG)) are often planted decoys. Focus on whether the actual port facility and city are identical.
    - If one document specifies a completely different city, port, or company, it is a MISMATCH.

    Field: {field_name}
    - SI Value: "{si_val}"
    - BL Value: "{bl_val}"

    Answer with ONLY the word "MATCH" or "MISMATCH".
    """
    try:
        response = client.models.generate_content(
            model="gemini-3.6-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.0,
                tools=[],
            ),
        )
        return "MATCH" in response.text.strip().upper()
    except Exception as err:
        print(f"[Warning] LLM verification fallback failed for {field_name}: {err}")
        return False


# =====================================================================
# 3. Field Comparison Logic
# =====================================================================

def compare_field(field_name: str, si_node: Dict[str, Any], bl_node: Dict[str, Any]) -> Discrepancy:
    si_raw = si_node.get("raw")
    bl_raw = bl_node.get("raw")
    si_norm = si_node.get("norm")
    bl_norm = bl_node.get("norm")

    # Missing field detection
    if si_norm is None or bl_norm is None:
        status = "Missing"
        if si_norm is None and bl_norm is None:
            status = "Match"
        return Discrepancy(
            field=field_name,
            status=status,
            si_raw=si_raw,
            bl_raw=bl_raw,
            si_norm=si_norm,
            bl_norm=bl_norm,
            verdict=status,
            notes="Field missing from one or both documents." if status == "Missing" else None
        )

    # 1. Numerical Comparison: gross_weight_kg
    if field_name == "gross_weight_kg":
        try:
            val_si = float(str(si_norm).replace(",", "").strip())
            val_bl = float(str(bl_norm).replace(",", "").strip())
            if abs(val_si - val_bl) <= 0.1:
                return Discrepancy(field=field_name, status="Match", si_raw=si_raw, bl_raw=bl_raw, si_norm=str(val_si), bl_norm=str(val_bl), verdict="Match")
            return Discrepancy(
                field=field_name,
                status="Mismatch",
                si_raw=si_raw,
                bl_raw=bl_raw,
                si_norm=str(val_si),
                bl_norm=str(val_bl),
                verdict="Mismatch",
                notes=f"Weight variance exceeds tolerance: SI={val_si} vs BL={val_bl}"
            )
        except (ValueError, TypeError):
            pass

    # 2. Count Comparison: container_count (extracts leading integer)
    if field_name == "container_count":
        match_si = re.search(r"\d+", str(si_norm))
        match_bl = re.search(r"\d+", str(bl_norm))
        c_si = match_si.group(0) if match_si else str(si_norm)
        c_bl = match_bl.group(0) if match_bl else str(bl_norm)
        if c_si == c_bl:
            return Discrepancy(field=field_name, status="Match", si_raw=si_raw, bl_raw=bl_raw, si_norm=si_norm, bl_norm=bl_norm, verdict="Match")
        return Discrepancy(
            field=field_name,
            status="Mismatch",
            si_raw=si_raw,
            bl_raw=bl_raw,
            si_norm=si_norm,
            bl_norm=bl_norm,
            verdict="Mismatch",
            notes=f"Container count mismatch: {c_si} vs {c_bl}"
        )

    # 3. Deterministic String Equality Check
    if str(si_norm).strip().upper() == str(bl_norm).strip().upper():
        return Discrepancy(field=field_name, status="Match", si_raw=si_raw, bl_raw=bl_raw, si_norm=si_norm, bl_norm=bl_norm, verdict="Match")

    # 4. LLM Semantic Fallback for Ports and Party Entities
    if field_name in {"port_of_loading", "port_of_discharge", "shipper", "consignee", "notify_party"}:
        if llm_verify_semantic_match(field_name, str(si_raw), str(bl_raw)):
            return Discrepancy(
                field=field_name,
                status="Match",
                si_raw=si_raw,
                bl_raw=bl_raw,
                si_norm=si_norm,
                bl_norm=bl_norm,
                verdict="Match",
                notes="Matched via semantic entity verification."
            )

    return Discrepancy(
        field=field_name,
        status="Mismatch",
        si_raw=si_raw,
        bl_raw=bl_raw,
        si_norm=si_norm,
        bl_norm=bl_norm,
        verdict="Mismatch",
        notes="Values do not match."
    )


# =====================================================================
# 4. Pipeline Runner
# =====================================================================

def compare_documents(si_doc: Dict[str, Any], bl_doc: Dict[str, Any]) -> ComparisonReport:
    email_id = si_doc.get("email_id") or bl_doc.get("email_id") or "unknown_email"
    si_fields = si_doc.get("fields", {})
    bl_fields = bl_doc.get("fields", {})

    all_field_names = sorted(set(si_fields.keys()) | set(bl_fields.keys()))
    rows: List[Discrepancy] = []

    for name in all_field_names:
        si_node = si_fields.get(name, {})
        bl_node = bl_fields.get(name, {})
        rows.append(compare_field(name, si_node, bl_node))

    mismatches = [r for r in rows if r.verdict == "Mismatch"]

    return ComparisonReport(
        email_id=email_id,
        match_status="DISCREPANCIES_FOUND" if mismatches else "CLEAN_MATCH",
        total_fields_checked=len(rows),
        discrepancies_count=len(mismatches),
        rows=rows
    )


# =====================================================================
# 5. Verification Test Suite
# =====================================================================

if __name__ == "__main__":
    # Test case matching the exact sample payload
    sample_si = {
        "email_id": "email_025",
        "declared_role": "SI",
        "fields": {
            "shipper": {
                "present": True,
                "raw": "APRIL FAR EAST (M) SDN BHD ",
                "norm": "APRIL FAR EAST (M) SDN BHD"
            },
            "consignee": {
                "present": True,
                "raw": "Cerivex    ",
                "norm": "CERIVEX"
            },
            "notify_party": {
                "present": True,
                "raw": "ROXCEL TRADING GMBH",
                "norm": "ROXCEL TRADING GMBH"
            },
            "port_of_loading": {
                "present": True,
                "raw": "PORT KLANG (WESTPORT   ), MALAYSIA (MYPKG )",
                "norm": "PORT KLANG (WESTPORT), MALAYSIA"
            },
            "port_of_discharge": {
                "present": True,
                "raw": "FREMANTLE, AUSTRALIA (AUFRE)",
                "norm": "FREMANTLE, AUSTRALIA"
            },
            "container_count": {
                "present": True,
                "raw": "6 x 20'GP",
                "norm": "6 X 20'GP"
            },
            "gross_weight_kg": {
                "present": True,
                "raw": "135,126 kg ",
                "norm": "135126"
            }
        }
    }

    # Paired Draft Bill of Lading with formatting/order differences
    sample_bl = {
        "email_id": "email_025",
        "declared_role": "BL",
        "fields": {
            "shipper": {
                "present": True,
                "raw": "APRIL FAR EAST (M) SDN BHD",
                "norm": "APRIL FAR EAST (M) SDN BHD"
            },
            "consignee": {
                "present": True,
                "raw": "CERIVEX",
                "norm": "CERIVEX"
            },
            "notify_party": {
                "present": True,
                "raw": "ROXCEL TRADING GMBH",
                "norm": "ROXCEL TRADING GMBH"
            },
            "port_of_loading": {
                "present": True,
                "raw": "MYPKG - PORT KLANG",
                "norm": "MYPKG - PORT KLANG"
            },
            "port_of_discharge": {
                "present": True,
                "raw": "AUFRE - FREMANTLE",
                "norm": "AUFRE - FREMANTLE"
            },
            "container_count": {
                "present": True,
                "raw": "6 CONTAINERS",
                "norm": "6"
            },
            "gross_weight_kg": {
                "present": True,
                "raw": "135126.00 KGS",
                "norm": "135126.0"
            }
        }
    }

    report = compare_documents(sample_si, sample_bl)

    print("=" * 65)
    print(f"REPORT STATUS  : {report.match_status}")
    print(f"FIELDS CHECKED : {report.total_fields_checked}")
    print(f"MISMATCHES     : {report.discrepancies_count}")
    print("=" * 65)
    for row in report.rows:
        print(f"[{row.verdict:<8}] {row.field:<20} | SI: {str(row.si_norm):<30} vs BL: {str(row.bl_norm):<20}")
        if row.notes:
            print(f"         └─ Note: {row.notes}")

    print("\nContract 5 JSON Report:")
    print(report.model_dump_json(indent=2))