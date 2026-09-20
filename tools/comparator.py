"""Lane C - Step 4: 100% Deterministic Document Comparison Engine.

Evaluates Shipping Instructions (SI) against Bills of Lading (BL).
Zero AI / zero API dependencies. Uses token normalization, numeric tolerances,
and decoy-stripping rules compliant with Contract 5.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Set
from pydantic import BaseModel, Field


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
# 2. Deterministic Field Evaluators
# =====================================================================

LOCODE_DECOY = re.compile(r"\s*\(([A-Z]{5})\)\s*|\b[A-Z]{2}[A-Z0-9]{3}\b", re.I)


def extract_meaningful_tokens(val: str | None) -> Set[str]:
    """Strips punctuation, LOCODE decoys, and decomposes text into comparable word tokens."""
    if not val:
        return set()
    cleaned = LOCODE_DECOY.sub("", val.upper())
    # Extract alphanumeric words with length >= 2
    tokens = set(re.findall(r"\b[A-Z0-9]{2,}\b", cleaned))
    return tokens


def evaluate_port_deterministic(field_name: str, si_raw: Optional[str], bl_raw: Optional[str], 
                                si_norm: Optional[str], bl_norm: Optional[str]) -> Discrepancy:
    """Compares ports using token intersection to handle inverted word orders seamlessly."""
    if not si_raw and not bl_raw:
        return Discrepancy(field=field_name, status="Match", si_raw=si_raw, bl_raw=bl_raw, si_norm=si_norm, bl_norm=bl_norm, verdict="Match")
    if not si_raw or not bl_raw:
        return Discrepancy(field=field_name, status="Missing", si_raw=si_raw, bl_raw=bl_raw, si_norm=si_norm, bl_norm=bl_norm, verdict="Missing")

    # Fast path: exact normalized string equality
    if str(si_norm).strip().upper() == str(bl_norm).strip().upper():
        return Discrepancy(field=field_name, status="Match", si_raw=si_raw, bl_raw=bl_raw, si_norm=si_norm, bl_norm=bl_norm, verdict="Match")

    # Order-independent token set comparison (handles "MALAYSIA, PORT KLANG" vs "PORT KLANG, MALAYSIA")
    si_tokens = extract_meaningful_tokens(si_norm or si_raw)
    bl_tokens = extract_meaningful_tokens(bl_norm or bl_raw)

    # If both sides reduce to the exact same set of words, or one is a direct subset of the other
    if si_tokens and bl_tokens and (si_tokens == bl_tokens or si_tokens.issubset(bl_tokens) or bl_tokens.issubset(si_tokens)):
        return Discrepancy(
            field=field_name,
            status="Match",
            si_raw=si_raw,
            bl_raw=bl_raw,
            si_norm=si_norm,
            bl_norm=bl_norm,
            verdict="Match",
            notes="Matched via token set equivalence."
        )

    return Discrepancy(
        field=field_name,
        status="Mismatch",
        si_raw=si_raw,
        bl_raw=bl_raw,
        si_norm=si_norm,
        bl_norm=bl_norm,
        verdict="Mismatch",
        notes=f"Port discrepancy: SI tokens {sorted(si_tokens)} != BL tokens {sorted(bl_tokens)}"
    )


def compare_field(field_name: str, si_node: Dict[str, Any], bl_node: Dict[str, Any]) -> Discrepancy:
    si_raw = si_node.get("raw")
    bl_raw = bl_node.get("raw")
    si_norm = si_node.get("norm")
    bl_norm = bl_node.get("norm")

    # Missing checks
    if si_norm is None or bl_norm is None:
        status = "Match" if (si_norm is None and bl_norm is None) else "Missing"
        return Discrepancy(
            field=field_name,
            status=status,
            si_raw=si_raw,
            bl_raw=bl_raw,
            si_norm=si_norm,
            bl_norm=bl_norm,
            verdict=status,
            notes="Field missing from document" if status == "Missing" else None
        )

    # 1. Ports: Use tokenized set evaluation
    if field_name in {"port_of_loading", "port_of_discharge"}:
        return evaluate_port_deterministic(field_name, si_raw, bl_raw, si_norm, bl_norm)

    # 2. Weights: Numeric comparison with float tolerance
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
                notes=f"Weight variance: SI={val_si} vs BL={val_bl}"
            )
        except (ValueError, TypeError):
            pass

    # 3. Counts: Leading integer comparison
    if field_name == "container_count":
        match_si = re.search(r"\d+", str(si_norm))
        match_bl = re.search(r"\d+", str(bl_norm))
        c_si = match_si.group(0) if match_si else str(si_norm).strip()
        c_bl = match_bl.group(0) if match_bl else str(bl_norm).strip()
        verdict = "Match" if c_si == c_bl else "Mismatch"
        return Discrepancy(
            field=field_name,
            status=verdict,
            si_raw=si_raw,
            bl_raw=bl_raw,
            si_norm=si_norm,
            bl_norm=bl_norm,
            verdict=verdict,
            notes=None if verdict == "Match" else f"Count mismatch: {c_si} != {c_bl}"
        )

    # 4. Strings & Identifiers (shipper, consignee, booking_number, notify_party)
    if str(si_norm).strip().upper() == str(bl_norm).strip().upper():
        return Discrepancy(field=field_name, status="Match", si_raw=si_raw, bl_raw=bl_raw, si_norm=si_norm, bl_norm=bl_norm, verdict="Match")

    return Discrepancy(
        field=field_name,
        status="Mismatch",
        si_raw=si_raw,
        bl_raw=bl_raw,
        si_norm=si_norm,
        bl_norm=bl_norm,
        verdict="Mismatch",
        notes="Normalized values do not match."
    )


# =====================================================================
# 3. Pipeline Runner
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


if __name__ == "__main__":
    sample_si = {
        "email_id": "email_025",
        "fields": {
            "shipper": {"raw": "APRIL FAR EAST (M) SDN BHD", "norm": "APRIL FAR EAST (M) SDN BHD"},
            "port_of_loading": {"raw": "MALAYSIA, PORT KLANG (MYPKG)", "norm": "PORT KLANG, MALAYSIA"},
            "container_count": {"raw": "6 x 20'GP", "norm": "6 X 20'GP"},
            "gross_weight_kg": {"raw": "135,126 kg", "norm": "135126"}
        }
    }

    sample_bl = {
        "email_id": "email_025",
        "fields": {
            "shipper": {"raw": "APRIL FAR EAST (M) SDN BHD", "norm": "APRIL FAR EAST (M) SDN BHD"},
            "port_of_loading": {"raw": "MYPKG - PORT KLANG, MALAYSIA", "norm": "PORT KLANG, MALAYSIA"},
            "container_count": {"raw": "6 CONTAINERS", "norm": "6"},
            "gross_weight_kg": {"raw": "135126.0 kg", "norm": "135126.0"}
        }
    }

    report = compare_documents(sample_si, sample_bl)
    print(f"Verdict: {report.match_status} | Discrepancies: {report.discrepancies_count}")
    for row in report.rows:
        print(f"  [{row.verdict:<8}] {row.field:<18} -> SI: {row.si_norm} | BL: {row.bl_norm}")