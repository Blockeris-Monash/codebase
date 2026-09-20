#!/usr/bin/env python3
"""Turn any attachment into the same {label: value} pairs.

Lane A. Text, Word and Excel need no third-party package — .docx and .xlsx
are ZIP archives of XML. PDF needs `pypdf`; without it a PDF reports
NotAttempted rather than pretending to be empty.

Downstream stages never learn which format a value came from.
"""
from __future__ import annotations

import html
import re
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import NamedTuple

from contract_types import FormatType, ParseStatusType
from labels import canonical_field
from read_edi import edi_title, read_edi

XML_TAG = re.compile(r"<[^>]+>")
CELL_SEPARATOR = " | "
LINE_BREAK = "\x00"
LabelledPairs = list[tuple[str, str]]


def read_txt(path: Path) -> LabelledPairs:
    """One `label: value` per line; an indented line continues the value above."""
    pairs: LabelledPairs = []
    for line in path.read_text(errors="replace").split("\n"):
        label, separator, value = line.partition(":")
        if separator:
            pairs.append((label.strip(), value.strip()))

    return pairs


def _cell_paragraphs(cell: str) -> str:
    """Word separates the lines of a party block with <w:br/> inside a single
    paragraph, so splitting on <w:p> is not enough. Join them with the same
    separator Excel uses, and a party name is the first segment either way."""
    marked = re.sub(r"<w:br\s*/?>", LINE_BREAK, cell)
    marked = re.sub(r"</w:p>", LINE_BREAK, marked)
    text = html.unescape(XML_TAG.sub("", marked))
    lines = [line.strip() for line in text.split(LINE_BREAK) if line.strip()]

    return CELL_SEPARATOR.join(lines)


def _docx_rows(path: Path) -> list[list[str]]:
    document = zipfile.ZipFile(path).read("word/document.xml").decode("utf8")
    rows = []
    for row in re.findall(r"<w:tr[ >].*?</w:tr>", document, re.S):
        cells = [_cell_paragraphs(c) for c in re.findall(r"<w:tc[ >].*?</w:tc>", row, re.S)]
        rows.append([c for c in cells if c])

    return [r for r in rows if r]


def _docx_paragraphs(path: Path) -> list[str]:
    document = zipfile.ZipFile(path).read("word/document.xml").decode("utf8")
    texts = ["".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", p))
             for p in re.findall(r"<w:p[ >].*?</w:p>", document, re.S)]

    return [html.unescape(t).strip() for t in texts if t.strip()]


def read_docx(path: Path) -> LabelledPairs:
    """Word stores the document as a table; fall back to `label: value`
    paragraphs when it does not."""
    rows = _docx_rows(path)
    if rows:
        return [(r[0], CELL_SEPARATOR.join(r[1:])) for r in rows if len(r) > 1]

    pairs: LabelledPairs = []
    for text in _docx_paragraphs(path):
        label, separator, value = text.partition(":")
        if separator:
            pairs.append((label.strip(), value.strip()))

    return pairs


def _shared_strings(archive: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []
    xml = archive.read("xl/sharedStrings.xml").decode("utf8")

    return [html.unescape(XML_TAG.sub("", item))
            for item in re.findall(r"<si>(.*?)</si>", xml, re.S)]


def _cell_text(cell: str, shared: list[str]) -> str:
    inline = re.search(r"<is>.*?<t[^>]*>([^<]*)</t>", cell, re.S)
    if inline:
        return html.unescape(inline.group(1))

    value = re.search(r"<v>([^<]*)</v>", cell)
    if value is None:
        return ""

    is_shared = re.search(r't="s"', cell) is not None

    return shared[int(value.group(1))] if is_shared else value.group(1)


def read_xlsx(path: Path) -> LabelledPairs:
    """Excel keeps most text in a shared-string table, referenced by index."""
    archive = zipfile.ZipFile(path)
    shared = _shared_strings(archive)
    sheet = next(n for n in archive.namelist() if n.startswith("xl/worksheets/sheet"))
    xml = archive.read(sheet).decode("utf8")

    pairs: LabelledPairs = []
    for row in re.findall(r"<row[ >].*?</row>", xml, re.S):
        cells = [_cell_text(c, shared)
                 for c in re.findall(r"<c[ >][^>]*?(?:/>|>.*?</c>)", row, re.S)]
        filled = [c for c in cells if c]
        if len(filled) > 1:
            pairs.append((filled[0], CELL_SEPARATOR.join(filled[1:])))

    return pairs


def _pdf_text(path: Path) -> str:
    """Raise ValueError on a broken PDF so read_document reports Unreadable
    without needing pypdf imported at module level."""
    from pypdf import PdfReader
    from pypdf.errors import PyPdfError

    try:
        return "\n".join(page.extract_text() or "" for page in PdfReader(path).pages)
    except PyPdfError as error:
        raise ValueError(f"pypdf could not read {path.name}") from error


# The container table repeats one row per container and would otherwise be
# collected as the value of its own column heading. Its totals are restated
# below it as "label: value", so the table itself carries nothing we need.
TABLE_START = "CONTAINER NO."
MINIMUM_FIELDS = 5


def _is_label(text: str) -> bool:
    return canonical_field(text) is not None


def _pdf_pairs(lines: list[str]) -> LabelledPairs:
    """Group a form layout into pairs.

    The PDFs put a label on its own line with the value on the lines beneath
    it, and restate the totals further down as "label: value". Three cases:

        "No. of Containers: 6 x 40'HC"   a complete pair
        "Consignee"                      a label; the value follows
        "43-45 METROPOLITAN ROAD"        part of the value being collected
    """
    pairs: LabelledPairs = []
    label: str | None = None
    collected: list[str] = []
    in_table = False

    for line in lines:
        before, colon, after = line.partition(":")
        is_pair = bool(colon and after.strip() and _is_label(before))

        if line.upper().startswith(TABLE_START):
            in_table = True
        if is_pair:
            in_table = False

        if is_pair or (not in_table and _is_label(line)):
            if label is not None:
                pairs.append((label, CELL_SEPARATOR.join(collected)))
            label, collected = (None, []) if is_pair else (line, [])
            if is_pair:
                pairs.append((before.strip(), after.strip()))
            continue

        if label is not None and not in_table:
            collected.append(line)

    if label is not None:
        pairs.append((label, CELL_SEPARATOR.join(collected)))

    return pairs


def read_pdf(path: Path) -> LabelledPairs:
    """Needs pypdf. Every PDF here is a FORM: the label sits on its own line
    above its value. A scanned or corrupt file yields no text, which the
    caller reads as Unreadable rather than as an empty document."""
    lines = [line.strip() for line in _pdf_text(path).split("\n") if line.strip()]
    pairs = _pdf_pairs(lines)
    found = {canonical_field(label) for label, _ in pairs} - {None}

    if len(found) < MINIMUM_FIELDS:
        raise ValueError(f"{path.name}: found only {len(found)} of the seven fields")

    return pairs


def txt_title(path: Path) -> str | None:
    return path.read_text(errors="replace").split("\n", 1)[0].strip() or None


def docx_title(path: Path) -> str | None:
    paragraphs = _docx_paragraphs(path)

    return paragraphs[0] if paragraphs else None


def xlsx_title(path: Path) -> str | None:
    """Excel has no title line; the first populated cell holds it."""
    pairs = read_xlsx(path)

    return pairs[0][0] if pairs else None


def pdf_title(path: Path) -> str | None:
    lines = [line.strip() for line in _pdf_text(path).split("\n") if line.strip()]

    return lines[0] if lines else None


class Reader(NamedTuple):
    """Everything one format needs. Adding a format is one entry here and
    nothing else - the two functions used to live in separate dispatch
    points, which could drift apart."""
    pairs: Callable[[Path], LabelledPairs]
    title: Callable[[Path], str | None]


READERS: dict[str, Reader] = {
    FormatType.Txt: Reader(read_txt, txt_title),
    FormatType.Docx: Reader(read_docx, docx_title),
    FormatType.Xlsx: Reader(read_xlsx, xlsx_title),
    FormatType.Pdf: Reader(read_pdf, pdf_title),
    FormatType.Edi: Reader(read_edi, edi_title),
}
MINIMUM_PAIRS = 3


def reader_for(path: Path) -> Reader | None:
    return READERS.get(path.suffix.lstrip(".").lower())


def document_title(path: Path) -> str | None:
    """The document's own declared title, wherever its format keeps it.

    Text puts it on line one, Excel in the first populated cell, Word in the
    first paragraph, PDF on the first extracted line. This is what makes
    wrong_doc_type detectable, so it must never fall back to the filename.
    """
    reader = reader_for(path)
    if reader is None:
        return None

    try:
        return reader.title(path)
    except (ImportError, zipfile.BadZipFile, OSError, ValueError, KeyError,
            StopIteration, IndexError):
        return None


def read_document(path: Path) -> tuple[str, LabelledPairs]:
    """Return (parse_status, pairs). Never raises - an attachment that cannot
    be read is a NEEDS_REVIEW case, not a crash."""
    reader = reader_for(path)
    if reader is None:
        return ParseStatusType.NotAttempted, []
    if not path.exists():
        return ParseStatusType.Missing, []

    try:
        pairs = reader.pairs(path)
    except ImportError:
        return ParseStatusType.NotAttempted, []
    except (zipfile.BadZipFile, OSError, ValueError, KeyError, StopIteration):
        return ParseStatusType.Unreadable, []

    if len(pairs) < MINIMUM_PAIRS:
        return ParseStatusType.Unreadable, pairs

    return ParseStatusType.Ok, pairs


def main() -> int:
    """Read any document and print what the pipeline would see.

        python3 tools/read_documents.py <file> [<file> ...]
    """
    import sys

    from make_fixtures import canonical_field, detect_doc_type

    paths = [Path(a) for a in sys.argv[1:]]
    if not paths:
        print(main.__doc__)
        return 2

    for path in paths:
        status, pairs = read_document(path)
        print(f"\n{'=' * 78}\n{path.name}   [{status}]   {len(pairs)} labelled pairs\n{'=' * 78}")
        if path.suffix.lstrip(".").lower() == FormatType.Txt:
            print(f"declared type: {detect_doc_type(path.read_text(errors='replace'))}")
        matched = 0
        for label, value in pairs:
            field = canonical_field(label)
            matched += field is not None
            marker = f"-> {field}" if field else ""
            print(f"  {label[:38]:40}{value[:30]:32}{marker}")
        print(f"\n  {matched} of these map to one of the seven compared fields")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
