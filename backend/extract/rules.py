#!/usr/bin/env python3
"""Rule-based extraction: Lane A's label/value pairs into the seven fields.

The deterministic counterpart to backend/extract/ai.py. Both produce the same
DocumentExtract, so either can feed the compare stage and the two can be
diffed field by field.
"""
from __future__ import annotations

import os
from pathlib import Path

from backend.compare.evidence import describe_blanks
from backend.contracts import (
    Attachment, ClassificationResult, ComparisonResult, DocumentExtract,
    DocumentRoleType, EmailRecord, ExtractedField, FIELD_NAMES,
    ParseStatusType, ReviewReasonType, Scenario, StatusType, SubmissionEntry,
    VerdictType,
)
from backend.compare.normalise import compare_row
from backend.read.documents import document_title, read_document
from backend.read.labels import canonical_field, detect_doc_type

FULL_CONFIDENCE = 1.0

def attachment_meta(path: str) -> Attachment:
    name = os.path.basename(path)
    role = DocumentRoleType.Si if f"_{DocumentRoleType.Si}." in name else DocumentRoleType.Bl

    return {"path": path, "declared_role": role,
            "format": name.rsplit(".", 1)[-1].lower()}


def email_record(email: dict[str, object]) -> EmailRecord:
    """Contract 1 — loader output, one per email."""
    sender = str(email["from"])

    return {
        "email_id": str(email["email_id"]),
        "from": sender,
        "sender_domain": sender.split("@")[-1],
        "subject": str(email["subject"]),
        "body": str(email["body"]),
        "attachments": [attachment_meta(str(a)) for a in email["attachments"]],
    }


def absent_fields() -> dict[str, ExtractedField]:
    return {f: {"present": False, "label_seen": None, "raw": None}
            for f in FIELD_NAMES}


def fields_from_pairs(pairs: list[tuple[str, str]]) -> dict[str, ExtractedField]:
    """Align whatever the reader produced onto the seven field names."""
    found: dict[str, tuple[str, str]] = {}
    for label, value in pairs:
        field = canonical_field(label)
        if field is not None and field not in found:
            found[field] = (label.strip(), value.strip())

    return {
        f: {"present": f in found,
            "label_seen": found[f][0] if f in found else None,
            "raw": found[f][1] if f in found else None}
        for f in FIELD_NAMES
    }


def document_extract(data_dir: str, email_id: str, meta: Attachment) -> DocumentExtract:
    """Contract 3 — one per attachment, whatever format it arrived in."""
    base: DocumentExtract = {
        "email_id": email_id,
        "declared_role": meta["declared_role"],
        "source_path": meta["path"],
        "format": meta["format"],
        "detected_doc_type": None,
        "parse_status": ParseStatusType.NotAttempted,
        "fields": absent_fields(),
    }
    path = Path(data_dir) / meta["path"]
    status, pairs = read_document(path)
    if status != ParseStatusType.Ok:
        return {**base, "parse_status": status}

    return {**base, "detected_doc_type": detect_doc_type(document_title(path) or ""),
            "parse_status": ParseStatusType.Ok, "fields": fields_from_pairs(pairs)}


def review_result(email_id: str, reason: str, evidence: str) -> ComparisonResult:
    """Contract 4, escalation form — no table, nothing was comparable."""
    return {"email_id": email_id, "status": StatusType.NeedsReview,
            "review_reason": reason, "rows": [], "defect_fields": [],
            "evidence": evidence}


def comparison_result(email_id: str, si: DocumentExtract,
                      bl: DocumentExtract) -> ComparisonResult:
    """Contract 4 — the seven-row table plus the verdict for one email.

    An absent value outranks a defect: a partial comparison cannot support a
    complete verdict, so the whole email escalates.
    """
    rows = [compare_row(f, si["fields"][f]["raw"], bl["fields"][f]["raw"])
            for f in FIELD_NAMES]
    absent = [r["field"] for r in rows if r["verdict"] == VerdictType.Missing]
    defects = [r["field"] for r in rows if r["verdict"] == VerdictType.Mismatch]

    if absent:
        blanks = [(r["field"], r["si_raw"], r["bl_raw"],
                   r["si_norm"] is None, r["bl_norm"] is None)
                  for r in rows if r["verdict"] == VerdictType.Missing]
        return {**review_result(email_id, ReviewReasonType.MissingValue,
                                describe_blanks(blanks)),
                "rows": rows}
    if defects:
        return {"email_id": email_id, "status": StatusType.Mismatch,
                "review_reason": None, "rows": rows, "defect_fields": defects,
                "evidence": f"differs after normalisation: {', '.join(defects)}"}

    return {"email_id": email_id, "status": StatusType.Ok, "review_reason": None,
            "rows": rows, "defect_fields": [],
            "evidence": f"No mismatch detected. All {len(FIELD_NAMES)} fields match after normalisation."}


def submission_entry(comparison: ComparisonResult, category: str) -> SubmissionEntry:
    """Contract 5 — exactly the sample_submission.json shape."""
    is_mismatch = comparison["status"] == StatusType.Mismatch

    return {"category": category, "status": comparison["status"],
            "review_reason": comparison["review_reason"],
            "has_defect": is_mismatch, "defect_fields": comparison["defect_fields"]}


def classification(email_id: str, scenario: Scenario,
                   evidence: str) -> ClassificationResult:
    """Contract 2. `decided_by` is read by the official scorer, which reports
    the share of decisions made by rule."""
    return {"email_id": email_id, "category": scenario["category"],
            "decided_by": scenario["decided_by"], "confidence": FULL_CONFIDENCE,
            "evidence": evidence}


