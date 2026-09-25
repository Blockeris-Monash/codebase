#!/usr/bin/env python3
"""Build frontend/results.js: every email with its category and, for SI vs BL emails,
the real comparison, so the review UI opens instantly and calls no model.

    python3 -m cli.make_results

Comparison uses the team's own stages: the reader (backend.read), the saved
extracts in results/extracts, the cleaner in backend.app, and the comparator.

Categories: the classifier is an LLM call with a small daily limit, so it cannot
be run over all 520 emails on demand. If results/classifications/<email_id>.json
exists (a ClassificationResult) it wins. Otherwise a plain fallback is used and
marked `decided_by: "fallback"`, so the UI never presents a guess as the AI.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dotenv import load_dotenv

import backend.app as pipeline
from backend.compare.comparator import compare
from backend.intent import about, email_intent
from backend.mail_view import DRAFT_REQUEST, clean_body, document, fallback_category, shipment_ref
from cli.demo_replies import demo_draft

# Loaded here rather than relied on second-hand: this worked only because
# importing backend.app happens to call load_dotenv, which breaks the moment
# that import goes away.
load_dotenv()

ROOT = Path(__file__).resolve().parents[1]


def role_of(path: str) -> str:
    return "SI" if "_SI." in Path(path).name else "BL"


def saved_status(email_id: str, role: str) -> str | None:
    return (pipeline.load_saved_extract(email_id, role) or {}).get("parse_status")


def compared(email_id: str, docs: dict) -> dict:
    """Run the same cache, clean, compare path as POST /extract-clean-compare."""
    prepared = {}
    for role in ("SI", "BL"):
        extract = pipeline.load_saved_extract(email_id, role) if role in docs else None
        prepared[role] = None if extract is None else {**extract, "fields": pipeline.apply_cleaner(extract["fields"])}
    return compare(email_id, prepared["SI"], prepared["BL"]).model_dump()


def build_email(inbox_file: Path, data_dir: Path, classifications: Path) -> dict:
    record = json.loads(inbox_file.read_text(encoding="utf-8"))
    email_id, body = record["email_id"], clean_body(record["body"])
    attachments = record["attachments"]
    entry = {"id": email_id, "from": record["from"], "subject": record["subject"], "body": body,
             "n_attachments": len(attachments)}

    ref = shipment_ref(record["subject"], record["body"])
    if ref:  # absent rather than null, so the UI can test for it plainly
        entry["ref"] = ref

    saved_class = classifications / f"{email_id}.json"
    if saved_class.exists():
        found = json.loads(saved_class.read_text(encoding="utf-8"))
        entry.update(category=found["category"], decided_by=found["decided_by"])
        for saved, shown in (("confidence", "class_confidence"), ("evidence", "class_evidence")):
            if found.get(saved) is not None:  # "evidence" is taken by the comparator, so these get their own names
                entry[shown] = found[saved]
    else:
        entry.update(category=fallback_category(record["subject"], record["body"], len(attachments)),
                     decided_by="fallback")

    if entry["category"] == "BL_COMPARISON":
        docs = {role_of(rel): document(data_dir / rel, saved_status(email_id, role_of(rel))) for rel in attachments}
        result = compared(email_id, docs)
        entry.update(status=result["status"], review_reason=result["review_reason"], rows=result["rows"],
                     defect_fields=result["defect_fields"], evidence=result["evidence"], docs=docs)
        if not attachments and DRAFT_REQUEST.search(record["body"]):
            entry["awaiting"] = True

    intent = email_intent(entry["category"], record["subject"], record["body"], awaiting=bool(entry.get("awaiting")))
    if intent:  # absent rather than null, as with ref: the page shows the subject instead
        entry["intent"] = intent
        entry["about"] = about(intent, record["subject"], record["body"])

    # Live mail drafts these two with the AI (backend/reply.py) when asked; the demo calls no
    # model, so it carries a draft Claude wrote in advance, shown behind the same Draft a reply.
    if entry["category"] in ("INVOICE_QUERY", "GENERAL"):
        draft = demo_draft(email_id)
        if draft:
            entry.update(can_draft=True, demo_draft=draft, draft_by="claude")
    return entry


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--data", default=str(ROOT / "data"))
    parser.add_argument("--extracts", default=str(ROOT / "results" / "extracts"))
    parser.add_argument("--classifications", default=str(ROOT / "results" / "classifications"))
    parser.add_argument("--out", default=str(ROOT / "frontend" / "results.js"))
    args = parser.parse_args()

    pipeline.EXTRACTS_DIR = Path(args.extracts)
    data_dir = Path(args.data)
    emails = [build_email(f, data_dir, Path(args.classifications)) for f in sorted((data_dir / "inbox").glob("email_*.json"))]
    emails.sort(key=lambda e: e["id"], reverse=True)  # the dataset has no dates, so id order stands in for newest first

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("const RESULTS = " + json.dumps(emails, ensure_ascii=False) + ";\n", encoding="utf-8", newline="\n")

    by_status = {}
    for e in emails:
        by_status[e.get("status", "none")] = by_status.get(e.get("status", "none"), 0) + 1
    print(f"{len(emails)} emails -> {out}   {by_status}")


if __name__ == "__main__":
    main()
