#!/usr/bin/env python3
"""Generate stage fixtures from the real dataset.

Every fixture is built from an actual email, so downstream stages are tested
against the data's real shape rather than an invented one. Which emails, and
why each was chosen, lives in `tools/Scenarios.json`.

    python3 tools/make_fixtures.py --data data --out fixtures
"""
from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path

from contract_types import (
    Attachment, CategoryType, ClassificationResult, ComparisonResult,
    DocumentExtract, DocumentRoleType, EmailRecord, ExtractedField,
    FIELD_NAMES, ParseStatusType, ReviewReasonType, Scenario,
    StatusType, SubmissionEntry, VerdictType,
)
from labels import canonical_field, detect_doc_type
from normalise import compare_row
from read_documents import document_title, read_document

DEFAULT_DATA_DIR = str(Path(__file__).resolve().parents[1] / "data")

SCENARIOS_PATH = Path(__file__).resolve().parent / "Scenarios.json"
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
        return {**review_result(email_id, ReviewReasonType.MissingValue,
                                f"no comparable value on one side for: {', '.join(absent)}"),
                "rows": rows}
    if defects:
        return {"email_id": email_id, "status": StatusType.Mismatch,
                "review_reason": None, "rows": rows, "defect_fields": defects,
                "evidence": f"differs after normalisation: {', '.join(defects)}"}

    return {"email_id": email_id, "status": StatusType.Ok, "review_reason": None,
            "rows": rows, "defect_fields": [],
            "evidence": f"all {len(FIELD_NAMES)} fields match after normalisation"}


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


# Phrases that decide a category, matched against the real body. Order
# matters: comparison phrases are tested before the weaker "draft BL" ones,
# because both mention a draft BL.
SPAM_DOMAINS = frozenset({
    "webmail-verify.co", "secure-mailbox.org", "parcel-track.co",
    "logistics-deals.biz", "prize-claims.info", "crypto-invest.net",
})
BODY_RULES: list[tuple[str, str]] = [
    ("Attached are the SI and draft BL", CategoryType.BlComparison),
    ("attached the shipping instruction and the draft bill of lading", CategoryType.BlComparison),
    ("check the draft BL against the SI", CategoryType.BlComparison),
    ("Please compare the SI and draft BL", CategoryType.BlComparison),
    ("Attached SI and draft BL", CategoryType.BlComparison),
    # Emails 501-505 attach an invoice, packing list or certificate of origin
    # in the BL slot. The sender still believes they are sending a BL, so this
    # is a comparison request - it just escalates as wrong_doc_type.
    ("attached the SI and the", CategoryType.BlComparison),
    ("Please find Shipping instruction", CategoryType.SiRequest),
    ("send the draft BL", CategoryType.SiRequest),
    ("D&D / detention charges", CategoryType.InvoiceQuery),
    ("GR is still missing for invoice", CategoryType.InvoiceQuery),
    ("Query on invoice", CategoryType.InvoiceQuery),
    ("Requesting to cancel invoice", CategoryType.InvoiceQuery),
    ("daily berthing report", CategoryType.General),
]
NO_RULE_MATCHED = "no rule matched"


def classify_from_body(email: dict[str, object]) -> tuple[str | None, str]:
    """Return (category, evidence) from the email's own text.

    Evidence quotes the phrase that actually matched, because that string is
    shown to a human reviewer and must therefore be true of this email.
    """
    domain = str(email["from"]).split("@")[-1]
    if domain in SPAM_DOMAINS:
        return CategoryType.Spam, f"sender domain {domain} is on the spam list"

    body = str(email["body"]).lower()
    matched = next((r for r in BODY_RULES if r[0].lower() in body), None)
    if matched is None:
        return None, NO_RULE_MATCHED

    return matched[1], f"body contains: {matched[0]!r}"


def escalation_for(si: DocumentExtract | None,
                   bl: DocumentExtract | None) -> tuple[str, str] | None:
    """Why this pair cannot be compared, or None if it can.

    Ordered by dependency: a document that is absent cannot be parsed, and one
    that will not parse cannot have its type checked.
    """
    if si is None or bl is None:
        present = sorted(d["declared_role"] for d in (si, bl) if d is not None)
        return ReviewReasonType.MissingAttachment, f"expected SI and BL, found {present}"
    unread = [d for d in (si, bl) if d["parse_status"] != ParseStatusType.Ok]
    if unread:
        detail = ", ".join(f"{d['declared_role']} ({d['parse_status']})" for d in unread)
        return ReviewReasonType.Unreadable, f"could not read: {detail}"
    if (si["detected_doc_type"], bl["detected_doc_type"]) != (DocumentRoleType.Si, DocumentRoleType.Bl):
        return (ReviewReasonType.WrongDocType,
                f"filename says SI/BL, document header says "
                f"{si['detected_doc_type']}/{bl['detected_doc_type']}")

    return None


REASONING_KEYS = ("why_chosen", "covers", "assert_this", "caveat")
NON_COMPARISON_ENTRY = {"status": StatusType.Ok, "review_reason": None,
                        "has_defect": False, "defect_fields": []}


def build(data_dir: str, email: dict[str, object]) -> tuple[EmailRecord,
                                                            list[DocumentExtract],
                                                            ComparisonResult]:
    """Every stage artefact for one email."""
    email_id = str(email["email_id"])
    record = email_record(email)
    extracts = [document_extract(data_dir, email_id, m) for m in record["attachments"]]
    by_role = {e["declared_role"]: e for e in extracts}

    escalation = escalation_for(by_role.get(DocumentRoleType.Si),
                                by_role.get(DocumentRoleType.Bl))
    if escalation is not None:
        return record, extracts, review_result(email_id, *escalation)

    comparison = comparison_result(email_id, by_role[DocumentRoleType.Si],
                                   by_role[DocumentRoleType.Bl])

    return record, extracts, comparison


def reasoning_block(scenario: Scenario) -> dict[str, str]:
    """The `_why` header, so the next person can tell a deliberate choice
    from an accident."""
    block = {"scenario": scenario["name"], "email_id": scenario["email_id"]}
    block.update({key: scenario[key] for key in REASONING_KEYS})

    return block


def evidence_for(email: dict[str, object], category: str) -> str:
    """Quote the phrase that actually matched. A fixture asserting a category
    the rules did not reach says so, rather than quietly disagreeing."""
    matched, evidence = classify_from_body(email)
    if matched == category:
        return evidence

    return f"{evidence}; FIXTURE OVERRIDE: rule said {matched}, fixture asserts {category}"


def entry_for(comparison: ComparisonResult, category: str) -> SubmissionEntry:
    """Non-comparison categories carry no verdict — classified, then stop."""
    if category == CategoryType.BlComparison:
        return submission_entry(comparison, category)

    return {"category": category, **NON_COMPARISON_ENTRY}


def build_bundle(data_dir: str, scenario: Scenario) -> tuple[dict[str, object],
                                                             SubmissionEntry]:
    email_id, category = scenario["email_id"], scenario["category"]
    email = json.loads((Path(data_dir) / "inbox" / f"{email_id}.json").read_text())
    record, extracts, comparison = build(data_dir, email)
    entry = entry_for(comparison, category)
    is_comparison = category == CategoryType.BlComparison
    bundle = {
        "_why": reasoning_block(scenario),
        "EmailRecord": record,
        "ClassificationResult": classification(email_id, scenario,
                                               evidence_for(email, category)),
        "DocumentExtract": extracts,
        "ComparisonResult": comparison if is_comparison else None,
        "SubmissionEntry": entry,
    }

    return bundle, entry


def load_scenarios() -> list[Scenario]:
    return json.loads(SCENARIOS_PATH.read_text())


def numbered(index: int, name: str) -> str:
    """Two-digit prefix so `ls` shows the fixtures in reading order."""
    return f"{index:02d}-{name}.json"


def write_fixtures(data_dir: str, out: Path) -> dict[str, SubmissionEntry]:
    submission: dict[str, SubmissionEntry] = {}
    for index, scenario in enumerate(load_scenarios(), start=1):
        bundle, entry = build_bundle(data_dir, scenario)
        submission[scenario["email_id"]] = entry
        filename = numbered(index, scenario["name"])
        (out / filename).write_text(json.dumps(bundle, indent=2) + "\n")
        print(f"{filename:34} {scenario['email_id']}  "
              f"{entry['status']:12} {entry['defect_fields']}")

    return dict(sorted(submission.items()))  # submission keyed by id


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default=DEFAULT_DATA_DIR,
                        help="folder holding inbox/ and attachments/")
    parser.add_argument("--out", default="fixtures")
    args = parser.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    submission = write_fixtures(args.data, out)
    (out / "SubmissionSample.json").write_text(json.dumps(submission, indent=2) + "\n")
    print(f"\n{len(submission)} fixtures + SubmissionSample.json -> {out}/")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
