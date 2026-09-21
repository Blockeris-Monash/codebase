#!/usr/bin/env python3
"""Showcase the readers: five input formats, one output shape.

    python3 -m cli.demo_read                    every format, side by side
    python3 -m cli.demo_read <file> [<file>]    one file, raw then parsed
    python3 -m cli.demo_read --raw              every format, raw then parsed

Lane A's whole job is that nothing downstream can tell what a value was
read from. This shows that happening, starting from what the file actually
contains - which for Word and Excel is a ZIP full of XML.
"""
from __future__ import annotations

import sys
import unicodedata
from pathlib import Path

from backend.contracts import FIELD_NAMES, ParseStatusType
from backend.read.labels import canonical_field
from backend.read.documents import READERS, document_title, read_document

ATTACHMENTS = Path(__file__).resolve().parents[1] / "data" / "attachments"
SAMPLES = Path(__file__).resolve().parents[1] / "tests" / "samples"
WIDE_CHARS = "WF"
ELLIPSIS = "…"
COLUMN_GAP = 2

FORMAT_NAMES = {"txt": "plain text", "docx": "Word", "xlsx": "Excel",
                "pdf": "PDF", "edi": "EDI X12"}
# One real file per supported format, so the showcase covers the table.
SHOWCASE = [
    ("txt", ATTACHMENTS / "email_064_SI.txt"),
    ("docx", ATTACHMENTS / "email_055_BL.docx"),
    ("xlsx", ATTACHMENTS / "email_055_SI.xlsx"),
    ("pdf", ATTACHMENTS / "email_059_SI.pdf"),
    ("edi", SAMPLES / "Edi304Sample.edi"),
]


def display_width(text: str) -> int:
    return sum(2 if unicodedata.east_asian_width(c) in WIDE_CHARS else 1
               for c in text)


def pad(text: str, width: int) -> str:
    room = width - COLUMN_GAP
    if display_width(text) > room:
        while display_width(text) > room - 1 and text:
            text = text[:-1]
        text += ELLIPSIS

    return text + " " * (width - display_width(text))


def fields_of(path: Path) -> tuple[str, dict[str, tuple[str, str]]]:
    """(status, {field: (the label this document used, the value)})."""
    status, pairs = read_document(path)
    found: dict[str, tuple[str, str]] = {}
    for label, value in pairs:
        field = canonical_field(label)
        if field is not None and field not in found:
            found[field] = (label, value)

    return status, found


RAW_LINES = 12
RAW_WIDTH = 86


def raw_preview(path: Path) -> list[str]:
    """What the file actually holds. Word and Excel are ZIP archives of XML,
    so their bytes are unreadable - we show the XML inside instead, because
    that is what the reader is really working from."""
    suffix = path.suffix.lstrip(".").lower()
    if suffix in ("txt", "edi"):
        lines = [l for l in path.read_text(errors="replace").split("\n")
                 if l.strip() and not l.startswith("#")]
        return lines[:RAW_LINES]
    if suffix == "pdf":
        from backend.read.documents import _pdf_text
        return [l for l in _pdf_text(path).split("\n") if l.strip()][:RAW_LINES]

    import re
    import zipfile
    inner = {"docx": "word/document.xml", "xlsx": "xl/worksheets/sheet1.xml"}[suffix]
    content_starts = {"docx": "<w:body", "xlsx": "<sheetData"}[suffix]
    with zipfile.ZipFile(path) as archive:
        name = next(n for n in archive.namelist()
                    if n == inner or n.startswith(inner[:12]))
        xml = archive.read(name).decode("utf8", errors="replace")

    # Skip the namespace declarations - they are half a screen of nothing.
    xml = re.sub(r"\s+", " ", xml[max(xml.find(content_starts), 0):])
    chunks = [xml[i:i + RAW_WIDTH] for i in range(0, min(len(xml), RAW_WIDTH * 7), RAW_WIDTH)]

    return [f"[{path.name} is a ZIP archive. {name} inside it, "
            f"from {content_starts} onward:]", *chunks]


def show_raw(path: Path) -> None:
    print(f"\n  WHAT THE FILE ACTUALLY CONTAINS")
    print(f"  {'\u2500' * 84}")
    for line in raw_preview(path):
        print(f"  \u2502 {line[:RAW_WIDTH]}")
    print(f"  \u2502 \u2026")


def show_one(path: Path, with_raw: bool = True) -> None:
    """Every pair the reader found, and which of the seven it maps to."""
    status, pairs = read_document(path)
    kind = FORMAT_NAMES.get(path.suffix.lstrip(".").lower(), path.suffix)
    print(f"\n╭{'─' * 86}╮")
    print(f"│ {pad(f'{path.name}   ·   {kind}   ·   {status}', 84)} │")
    print(f"╰{'─' * 86}╯")
    if status != ParseStatusType.Ok:
        print("  could not be read - escalates to a human")
        return

    if with_raw:
        show_raw(path)
        print(f"\n  WHAT THE READER GETS OUT OF IT")
        print(f"  {'\u2500' * 84}")
    print(f"  the document calls itself {document_title(path)!r}")
    print(f"\n  {pad('label the document used', 40)}{pad('value', 32)}we call it")
    print(f"  {'─' * 84}")
    for label, value in pairs:
        field = canonical_field(label)
        arrow = f"→  {field}" if field else ""
        print(f"  {pad(label, 40)}{pad(value, 32)}{arrow}")
    matched = sum(1 for label, _ in pairs if canonical_field(label))
    print(f"\n  {matched} of {len(pairs)} pairs are one of the seven compared fields")


def show_all() -> None:
    """The point of Lane A: different formats in, identical shape out."""
    available = [(fmt, path) for fmt, path in SHOWCASE if path.exists()]
    print(f"\n{'═' * 92}")
    print("  FIVE INPUT FORMATS, ONE OUTPUT SHAPE")
    print(f"{'═' * 92}\n")

    for fmt, path in available:
        status, found = fields_of(path)
        print(f"  {pad(FORMAT_NAMES[fmt], 14)}{pad(path.name, 26)}"
              f"{pad(status, 8)}{len(found)} of 7 fields")
    print(f"\n  Every one of those produced the same thing - a list of "
          f"(label, value) pairs.\n  Nothing after this point can tell them apart.\n")

    print(f"{'─' * 92}")
    print("  THE LABEL EACH FORMAT USED FOR THE SAME FIELD")
    print(f"{'─' * 92}")
    print(f"  {pad('field', 20)}" + "".join(pad(FORMAT_NAMES[f], 17) for f, _ in available))
    print(f"  {'─' * 88}")

    read = {fmt: fields_of(path)[1] for fmt, path in available}
    for field in FIELD_NAMES:
        cells = "".join(pad(read[fmt].get(field, ("-", ""))[0], 17) for fmt, _ in available)
        print(f"  {pad(field, 20)}{cells}")

    print(f"\n  Seven fields. Five formats. Twenty-plus different label spellings,")
    print("  two written languages, and one of them is not a document at all.")
    print("\n  The EDI column is the one place the label is ours: an X12 file has no")
    print("  labels, only segment codes, so the reader names them on the way out -")
    print("  N1*SF becomes Shipper, R4*L becomes Port of Loading.\n")


def main() -> int:
    arguments = sys.argv[1:]
    if arguments == ["--raw"]:
        for _, path in SHOWCASE:
            if path.exists():
                show_one(path)
        return 0
    if not arguments:
        show_all()
        return 0

    for path in [Path(a) for a in arguments]:
        show_one(path)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
