"""When all seven fields match, the result says "No mismatch detected." (#162 A2).

The brief: 'If all seven fields match, report "No mismatch detected."' The comparator's
evidence and the page said "All 7 fields match" instead, so the exact phrase was nowhere.
"""
from __future__ import annotations

import json
from pathlib import Path

from backend.compare.comparator import compare

ROOT = Path(__file__).resolve().parents[1]
NO_MISMATCH = "No mismatch detected."


def doc(role: str) -> dict:
    fields = {f: {"present": True, "raw": v} for f, v in {
        "shipper": "ACME", "consignee": "BETA", "notify_party": "BETA", "port_of_loading": "SINGAPORE",
        "port_of_discharge": "BUSAN", "container_count": "1 x 40'HC", "gross_weight_kg": "1,000 KG"}.items()}
    return {"email_id": "email_001", "role": role, "detected_doc_type": role, "parse_status": "ok", "fields": fields}


def test_the_comparator_says_no_mismatch_detected_when_all_seven_match() -> None:
    result = compare("email_001", doc("SI"), doc("BL"))

    assert result.status == "OK"
    assert result.evidence.startswith(NO_MISMATCH)


def test_every_saved_verified_email_says_it() -> None:
    src = (ROOT / "frontend" / "results.js").read_text(encoding="utf-8")
    ok = [e for e in json.loads(src[src.index("["): src.rindex("]") + 1]) if e.get("status") == "OK"]

    assert len(ok) == 63
    assert all(e["evidence"].startswith(NO_MISMATCH) for e in ok)


def test_the_verified_banner_says_it() -> None:
    index = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    assert f'<div class="banner OK">${{ICON.OK}}${{t("{NO_MISMATCH}")}}' in index
