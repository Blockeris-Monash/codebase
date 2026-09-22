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
import re
from pathlib import Path

from dotenv import load_dotenv

import backend.app as pipeline
from backend.compare.comparator import compare
from backend.read.documents import document_title, read_document

# Loaded here rather than relied on second-hand: this worked only because
# importing backend.app happens to call load_dotenv, which breaks the moment
# that import goes away.
load_dotenv()

ROOT = Path(__file__).resolve().parents[1]
BODY_LIMIT = 1500

COMPARE_ASK = re.compile(
    r"(check|verify|compare|confirm)\w*\b.{0,40}\bdraft\s+BL\b.{0,40}\b(against|with|vs\.?)\b.{0,20}\bSI\b",
    re.I | re.S,
)
# An email that asks someone to send the draft BL and has nothing attached. There is nothing to
# compare yet, so the UI files it under its own folder instead of Needs review.
DRAFT_REQUEST = re.compile(r"\b(send|provide)\b.{0,30}\bdraft\s+BL\b", re.I | re.S)
SPAM = re.compile(r"bitcoin|exclusive offer|storage is|valued customer|increase your|approval required|prize|winner", re.I)
INVOICE = re.compile(r"invoice|billing|charges|debit note|payment|\bsoa\b", re.I)
SI_ASK = re.compile(r"\bSI\b|shipping instruction|draft\s+BL", re.I)

# The shipment a message is about, so a reviewer can answer "Commercial is asking about
# 5ALT-01226" without opening anything. Two shapes appear in this corpus and nothing else
# does: an order reference (5ALT-01226) and a carrier booking reference (OOLU9284044566).
#
# The carrier half demands a run of four digits. Without it, "[A-Z]{4}[A-Z0-9]{6,}" also
# matches INTERNATIONAL, OUTSTANDING and INVESTMENT - 13 English words in these subjects
# alone, every one of them a false reference on a reviewer's screen.
SHIPMENT_REF = re.compile(r"\b(?:\d[A-Z]{3}-\d{4,6}|[A-Z]{4}[A-Z0-9]*\d{4,}[A-Z0-9]*)\b")


def shipment_ref(subject: str, body: str) -> str | None:
    """The shipment this email is about, or None.

    Subject before body, and first match within each, so the reference shown on a row is
    the one already visible in the list rather than something found further down.
    """
    for text in (subject, body):
        found = SHIPMENT_REF.search((text or "").upper())
        if found:
            return found.group(0)
    return None


def fallback_category(subject: str, body: str, n_attachments: int) -> str:
    if n_attachments >= 1 or COMPARE_ASK.search(body):
        return "BL_COMPARISON"
    text = f"{subject} {body[:300]}"
    if SPAM.search(text):
        return "SPAM"
    if INVOICE.search(text):
        return "INVOICE_QUERY"
    if SI_ASK.search(text):
        return "SI_REQUEST"
    return "GENERAL"


def clean_body(body: str) -> str:
    return re.sub(r"\n{3,}", "\n\n", body).strip()[:BODY_LIMIT]


def role_of(path: str) -> str:
    return "SI" if "_SI." in Path(path).name else "BL"


def document(path: Path, email_id: str, role: str) -> dict:
    """What the UI needs from one attachment: shown text, and the inputs for a live re-check."""
    saved = pipeline.load_saved_extract(email_id, role)
    out = {"name": path.name, "format": path.suffix.lstrip("."), "title": None, "pairs": [],
           "text": None, "parse_status": (saved or {}).get("parse_status", "ok")}
    try:
        out["title"] = document_title(path)
        _, pairs = read_document(path)
        out["pairs"] = [list(p) for p in pairs]
    except Exception:  # unreadable files are Lane A's escalation, the comparator handles them
        out["parse_status"] = "unreadable" if not saved else out["parse_status"]
    if path.suffix == ".txt":
        out["text"] = path.read_text(encoding="utf-8", errors="replace")
    elif out["pairs"]:
        out["text"] = "\n".join(f"{label}: {value}" for label, value in out["pairs"])
    return out


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
        docs = {role_of(rel): document(data_dir / rel, email_id, role_of(rel)) for rel in attachments}
        result = compared(email_id, docs)
        entry.update(status=result["status"], review_reason=result["review_reason"], rows=result["rows"],
                     defect_fields=result["defect_fields"], evidence=result["evidence"], docs=docs)
        if not attachments and DRAFT_REQUEST.search(record["body"]):
            entry["awaiting"] = True
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
    out.write_text("const RESULTS = " + json.dumps(emails, ensure_ascii=False) + ";\n", encoding="utf-8")

    by_status = {}
    for e in emails:
        by_status[e.get("status", "none")] = by_status.get(e.get("status", "none"), 0) + 1
    print(f"{len(emails)} emails -> {out}   {by_status}")


if __name__ == "__main__":
    main()
