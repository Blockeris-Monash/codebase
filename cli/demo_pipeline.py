#!/usr/bin/env python3
"""Walk one email through every stage and print what each one did.

    python3 -m cli.demo_pipeline email_025          a defect
    python3 -m cli.demo_pipeline email_055          Excel SI against a Word BL
    python3 -m cli.demo_pipeline email_501          the BL is a commercial invoice
    python3 -m cli.demo_pipeline --data data email_064

Built for the demo and for debugging: when a verdict looks wrong, this
shows which stage made it wrong.
"""
from __future__ import annotations

import argparse
import json
import unicodedata
from pathlib import Path

from backend.contracts import FIELD_NAMES, ParseStatusType, StatusType
from backend.read.labels import canonical_field
from cli.make_fixtures import build, classify_from_body
from backend.read.documents import document_title, read_document

DEFAULT_DATA_DIR = str(Path(__file__).resolve().parents[1] / "data")

WIDTH = 96
FORMAT_NAMES = {"txt": "plain text", "docx": "Word", "xlsx": "Excel",
                "pdf": "PDF", "edi": "EDI X12"}
VERDICT_MARK = {"match": "  ", "mismatch": " \u2718", "missing": " ?"}
STATUS_LINE = {
    StatusType.Ok: "No mismatch detected",
    StatusType.Mismatch: "MISMATCH",
    StatusType.NeedsReview: "NEEDS REVIEW",
}


WIDE_CHARS = "WF"


ELLIPSIS = "\u2026"
COLUMN_GAP = 2


def display_width(text: str) -> int:
    """CJK characters occupy two terminal columns, so len() leaves these
    tables ragged."""
    return sum(2 if unicodedata.east_asian_width(c) in WIDE_CHARS else 1
               for c in text)


def pad(text: str, width: int) -> str:
    """Fit to a column, marking the cut and always leaving a gap."""
    room = width - COLUMN_GAP
    if display_width(text) > room:
        while display_width(text) > room - 1 and text:
            text = text[:-1]
        text += ELLIPSIS

    return text + " " * (width - display_width(text))


def banner(text: str) -> None:
    print(f"\n\u256d{'\u2500' * (WIDTH - 2)}\u256e")
    print(f"\u2502 {text:<{WIDTH - 4}} \u2502")
    print(f"\u2570{'\u2500' * (WIDTH - 2)}\u256f")


def stage(number: int, name: str, detail: str = "") -> None:
    print(f"\n  \u25b6 STAGE {number} \u2014 {name.upper()}   {detail}")
    print(f"  {'\u2500' * (WIDTH - 4)}")


def show_email(email: dict[str, object]) -> None:
    banner(f"{email['email_id']}   \u00b7   from {email['from']}")
    print(f"  {str(email['subject'])[:WIDTH - 4]}")


def show_classification(email: dict[str, object]) -> str | None:
    category, evidence = classify_from_body(email)
    stage(1, "classify", f"\u2192  {category or 'no rule matched'}")
    print(f"     because the {evidence}")
    print(f"     only BL_COMPARISON continues past here")

    return category


def show_reading(data_dir: str, extracts: list[dict[str, object]]) -> None:
    formats = {FORMAT_NAMES.get(str(e["format"]), str(e["format"])) for e in extracts}
    note = ("TWO DIFFERENT APPLICATIONS" if len(formats) > 1
            else f"both {formats.pop()}")
    stage(2, "read the files", f"\u2192  {note}")
    for extract in extracts:
        path = Path(data_dir) / str(extract["source_path"])
        status = str(extract["parse_status"])
        _, pairs = read_document(path) if status == ParseStatusType.Ok else (None, [])
        kind = FORMAT_NAMES.get(str(extract["format"]), str(extract["format"]))
        print(f"     {extract['declared_role']}   {path.name:26}{kind:12}"
              f"{status:14}{len(pairs):>2} label/value pairs")
        title = document_title(path) if status == ParseStatusType.Ok else None
        flag = "" if extract["detected_doc_type"] in ("SI", "BL") else "   \u2718 NOT A BILL OF LADING"
        print(f"         the document calls itself {str(title)!r}{flag}")


def show_extraction(extracts: list[dict[str, object]]) -> None:
    usable = [e for e in extracts if e["parse_status"] == ParseStatusType.Ok]
    if len(usable) < 2:
        return
    by_role = {e["declared_role"]: e for e in usable}
    landed = sum(1 for f in FIELD_NAMES
                 if all(by_role[r]["fields"][f]["present"] for r in ("SI", "BL")))
    note = ("every label differs, every field lands" if landed == len(FIELD_NAMES)
            else f"only {landed} of {len(FIELD_NAMES)} fields found on both sides")
    stage(3, "align by meaning", f"\u2192  {note}")
    print(f"     {'the two documents say':60}{'we call it'}")
    print(f"     {'\u2500' * (WIDTH - 6)}")
    for field in FIELD_NAMES:
        si = str(by_role["SI"]["fields"][field]["label_seen"] or "-")
        bl = str(by_role["BL"]["fields"][field]["label_seen"] or "-")
        print(f"     {pad(si, 29)}{pad(bl, 31)}\u2192  {field}")


def show_comparison(comparison: dict[str, object]) -> None:
    rows = comparison["rows"]
    if not rows:
        stage(4, "compare", "\u2192  nothing comparable")
        return

    stage(4, "compare", "\u2192  SI is the reference, BL is checked against it")
    print(f"       {'field':20}{'SI':30}{'BL':30}")
    print(f"     {'-' * (WIDTH - 7)}")
    for row in rows:
        mark = VERDICT_MARK[str(row["verdict"])]
        print(f"   {mark}  {pad(str(row['field']), 20)}"
              f"{pad(str(row['si_raw']), 30)}{pad(str(row['bl_raw']), 30)}")
        if (row["si_norm"], row["bl_norm"]) != (row["si_raw"], row["bl_raw"]):
            print(f"       {'':20}{pad(str(row['si_norm']), 30)}"
                  f"{pad(str(row['bl_norm']), 30)}\u2190 normalised")


def show_verdict(comparison: dict[str, object], entry: dict[str, object]) -> None:
    stage(5, "verdict", f"\u2192  {STATUS_LINE[str(comparison['status'])]}")
    print(f"     {comparison['evidence']}")
    print()
    print("     submission.json entry:")
    for line in json.dumps(entry, indent=2).split("\n"):
        print(f"       {line}")


def submission_entry(comparison: dict[str, object], category: str | None) -> dict[str, object]:
    is_mismatch = comparison["status"] == StatusType.Mismatch

    return {"category": category, "status": comparison["status"],
            "review_reason": comparison["review_reason"],
            "has_defect": is_mismatch, "defect_fields": comparison["defect_fields"]}


def run(data_dir: str, email_id: str) -> int:
    path = Path(data_dir) / "inbox" / f"{email_id}.json"
    if not path.exists():
        raise SystemExit(f"no such email: {path}")

    email = json.loads(path.read_text())
    show_email(email)
    category = show_classification(email)

    if not email["attachments"]:
        stage(2, "read the files", "\u2192  no attachments, classified and stops here")
        return 0

    _, extracts, comparison = build(data_dir, email)
    show_reading(data_dir, extracts)
    show_extraction(extracts)
    show_comparison(comparison)
    show_verdict(comparison, submission_entry(comparison, category))

    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("email_id")
    parser.add_argument("--data", default=DEFAULT_DATA_DIR)
    args = parser.parse_args()

    return run(args.data, args.email_id)


if __name__ == "__main__":
    raise SystemExit(main())
