"""Typed shapes for the five stage contracts.

Mirrors `contracts/0N-*.schema.json`. The schema stays authoritative — these
exist so the pipeline is type-checked and editors complete field names. When
a schema changes, change the matching TypedDict in the same commit.
"""
from __future__ import annotations

from enum import StrEnum
from typing import TypedDict


class CategoryType(StrEnum):
    BlComparison = "BL_COMPARISON"
    SiRequest = "SI_REQUEST"
    InvoiceQuery = "INVOICE_QUERY"
    General = "GENERAL"
    Spam = "SPAM"


class StatusType(StrEnum):
    Ok = "OK"
    Mismatch = "MISMATCH"
    NeedsReview = "NEEDS_REVIEW"


class ReviewReasonType(StrEnum):
    WrongDocType = "wrong_doc_type"
    MissingAttachment = "missing_attachment"
    Unreadable = "unreadable"
    MissingValue = "missing_value"


class VerdictType(StrEnum):
    Match = "match"
    Mismatch = "mismatch"
    Missing = "missing"


class ParseStatusType(StrEnum):
    Ok = "ok"
    Unreadable = "unreadable"
    Missing = "missing"
    NotAttempted = "not_attempted"


class FormatType(StrEnum):
    Txt = "txt"
    Pdf = "pdf"
    Docx = "docx"
    Xlsx = "xlsx"
    Edi = "edi"     # X12 304; not in the dataset, supported to show the
                    # extract stage is format-independent


class DocumentRoleType(StrEnum):
    Si = "SI"
    Bl = "BL"


class DecidedByType(StrEnum):
    Rule = "rule"
    Llm = "llm"


FIELD_NAMES: tuple[str, ...] = (
    "shipper", "consignee", "notify_party", "port_of_loading",
    "port_of_discharge", "container_count", "gross_weight_kg",
)


class Attachment(TypedDict):
    path: str
    declared_role: str
    format: str


# Functional syntax: "from" is a reserved word and cannot be a class attribute.
EmailRecord = TypedDict("EmailRecord", {
    "email_id": str,
    "from": str,
    "sender_domain": str,
    "subject": str,
    "body": str,
    "attachments": list[Attachment],
})
"""Contract 1 — loader output."""


class ClassificationResult(TypedDict):
    """Contract 2 — one per email, all 520."""
    email_id: str
    category: str
    decided_by: str
    confidence: float
    evidence: str


class ExtractedField(TypedDict):
    present: bool
    label_seen: str | None
    raw: str | None


class DocumentExtract(TypedDict):
    """Contract 3 — one per attachment."""
    email_id: str
    declared_role: str
    source_path: str
    format: str
    detected_doc_type: str | None
    parse_status: str
    fields: dict[str, ExtractedField]


class ComparisonRow(TypedDict):
    field: str
    si_raw: str | None
    bl_raw: str | None
    si_norm: str | None
    bl_norm: str | None
    verdict: str


class ComparisonResult(TypedDict):
    """Contract 4 — the seven-row table."""
    email_id: str
    status: str
    review_reason: str | None
    rows: list[ComparisonRow]
    defect_fields: list[str]
    evidence: str


class SubmissionEntry(TypedDict):
    """Contract 5 — exactly the sample_submission.json shape."""
    category: str
    status: str
    review_reason: str | None
    has_defect: bool
    defect_fields: list[str]


class Scenario(TypedDict):
    """One entry of tools/Scenarios.json — which email a fixture uses and why."""
    name: str
    email_id: str
    category: str
    decided_by: str
    classification_evidence: str
    why_chosen: str
    covers: str
    assert_this: str
    caveat: str
