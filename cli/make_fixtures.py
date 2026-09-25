#!/usr/bin/env python3
"""Generate stage fixtures from the real dataset.

Every fixture is built from an actual email, so downstream stages are tested
against the data's real shape rather than an invented one. Which emails, and
why each was chosen, lives in `cli/Scenarios.json`.

    python3 -m cli.make_fixtures --data data --out fixtures
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from backend.contracts import (
    CategoryType, ComparisonResult, DocumentExtract, DocumentRoleType,
    EmailRecord, ParseStatusType, ReviewReasonType, Scenario, StatusType,
    SubmissionEntry,
)
from backend.extract.rules import (
    classification, comparison_result, document_extract, email_record,
    review_result, submission_entry,
)

DEFAULT_DATA_DIR = str(Path(__file__).resolve().parents[1] / "data")
SCENARIOS_PATH = Path(__file__).resolve().parent / "Scenarios.json"

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
    """Non-comparison categories carry no verdict: classified, then stop."""
    if category == CategoryType.BlComparison:
        return submission_entry(comparison, category)

    return {"category": category, **NON_COMPARISON_ENTRY}


def build_bundle(data_dir: str, scenario: Scenario) -> tuple[dict[str, object],
                                                             SubmissionEntry]:
    email_id, category = scenario["email_id"], scenario["category"]
    email = json.loads((Path(data_dir) / "inbox" / f"{email_id}.json").read_text(encoding="utf-8"))
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
    return json.loads(SCENARIOS_PATH.read_text(encoding="utf-8"))


def numbered(index: int, name: str) -> str:
    """Two-digit prefix so `ls` shows the fixtures in reading order."""
    return f"{index:02d}-{name}.json"


def write_fixtures(data_dir: str, out: Path) -> dict[str, SubmissionEntry]:
    submission: dict[str, SubmissionEntry] = {}
    for index, scenario in enumerate(load_scenarios(), start=1):
        bundle, entry = build_bundle(data_dir, scenario)
        submission[scenario["email_id"]] = entry
        filename = numbered(index, scenario["name"])
        (out / filename).write_text(json.dumps(bundle, indent=2) + "\n", encoding="utf-8", newline="\n")
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
    (out / "SubmissionSample.json").write_text(json.dumps(submission, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"\n{len(submission)} fixtures + SubmissionSample.json -> {out}/")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
