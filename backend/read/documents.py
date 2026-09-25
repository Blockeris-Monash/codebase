"""Turn any attachment into the same {label: value} pairs.

Lane A. Text, Word and Excel need no third-party package — .docx and .xlsx
are ZIP archives of XML. PDF needs `pypdf`; without it a PDF reports
NotAttempted rather than pretending to be empty.

Downstream stages never learn which format a value came from.
"""
from __future__ import annotations

import html
import logging
import re
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import NamedTuple

from backend.contracts import FormatType, ParseStatusType
from backend.read.labels import canonical_field
from backend.read.edi import edi_title, read_edi

log = logging.getLogger(__name__)

XML_TAG = re.compile(r"<[^>]+>")
CELL_SEPARATOR = " | "
LINE_BREAK = "\x00"
LabelledPairs = list[tuple[str, str]]

# Every way a file can defeat a reader. One tuple, because these used to
# be written out twice and IndexError was in only one of them - which made
# read_document raise on an .xlsx with a dangling shared-string index.
UNREADABLE_ERRORS = (zipfile.BadZipFile, OSError, ValueError, KeyError,
                     StopIteration, IndexError)

# A .docx or .xlsx is a ZIP, and a 5 MB upload can inflate to gigabytes (a zip bomb).
# The largest member in the dataset is 438 KB; nothing a shipper writes comes near this.
MAX_MEMBER_BYTES = 8 * 1024 * 1024
# Every SI and BL in the dataset is one page. Reading stops here, so a PDF of
# thousands of pages cannot hold the service up.
MAX_PDF_PAGES = 20


def _read_member(archive: zipfile.ZipFile, name: str) -> str:
    """One XML part of the archive, refused past MAX_MEMBER_BYTES. The declared size
    is checked first, then the read itself is capped, since the header can lie."""
    if archive.getinfo(name).file_size > MAX_MEMBER_BYTES:
        raise ValueError(f"{name} inflates past {MAX_MEMBER_BYTES} bytes")
    with archive.open(name) as member:
        data = member.read(MAX_MEMBER_BYTES + 1)
    if len(data) > MAX_MEMBER_BYTES:
        raise ValueError(f"{name} inflates past {MAX_MEMBER_BYTES} bytes")

    return data.decode("utf8")


def read_txt(path: Path) -> LabelledPairs:
    """One `label: value` per line. An indented line continues the value above, and a
    label with nothing after its colon takes the colon-free lines beneath it, so a blank
    label never swallows the next one; a blank line ends a value. An unindented line under a filled value is not taken: under Gross Weight it
    would reach the weight parser (#147 B3)."""
    pairs: LabelledPairs = []
    is_open = False
    for line in path.read_text(encoding="utf-8", errors="replace").split("\n"):
        text = line.strip()
        if not text:
            is_open = False
            continue
        if is_open and (line[0].isspace() or (not pairs[-1][1] and ":" not in line)):
            label, value = pairs[-1]
            pairs[-1] = (label, f"{value}\n{text}" if value else text)
            continue
        label, separator, value = line.partition(":")
        is_open = bool(separator)
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
    with zipfile.ZipFile(path) as archive:
        document = _read_member(archive, "word/document.xml")
    rows = []
    for row in re.findall(r"<w:tr[ >].*?</w:tr>", document, re.S):
        cells = [_cell_paragraphs(c) for c in re.findall(r"<w:tc[ >].*?</w:tc>", row, re.S)]
        rows.append([c for c in cells if c])

    return [r for r in rows if r]


def _docx_paragraphs(path: Path) -> list[str]:
    with zipfile.ZipFile(path) as archive:
        document = _read_member(archive, "word/document.xml")
    texts = ["".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", p))
             for p in re.findall(r"<w:p[ >].*?</w:p>", document, re.S)]

    return [html.unescape(t).strip() for t in texts if t.strip()]


def row_pairs(cells: list[str]) -> LabelledPairs:
    """The pairs in one table row, from its filled cells. "Shipper | X | Consignee | Y" is
    two; the whole row after the first cell used to be the shipper (#147 B3). A row that
    does not start with a known label keeps the first-cell-is-the-label reading."""
    if len(cells) < 2:
        return []
    starts = [0]
    if _is_label(cells[0]):
        starts += [i for i in range(1, len(cells) - 1) if _is_label(cells[i])]
    ends = starts[1:] + [len(cells)]

    return [(cells[start], CELL_SEPARATOR.join(cells[start + 1:end])) for start, end in zip(starts, ends)]


def read_docx(path: Path) -> LabelledPairs:
    """Word stores the document as a table; fall back to `label: value`
    paragraphs when it does not."""
    rows = _docx_rows(path)
    if rows:
        return [pair for row in rows for pair in row_pairs(row)]

    pairs: LabelledPairs = []
    for text in _docx_paragraphs(path):
        label, separator, value = text.partition(":")
        if separator:
            pairs.append((label.strip(), value.strip()))

    return pairs


def _shared_strings(archive: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []
    xml = _read_member(archive, "xl/sharedStrings.xml")

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
    with zipfile.ZipFile(path) as archive:
        shared = _shared_strings(archive)
        sheet = next(n for n in archive.namelist()
                     if n.startswith("xl/worksheets/sheet"))
        xml = _read_member(archive, sheet)

    pairs: LabelledPairs = []
    for row in re.findall(r"<row[ >].*?</row>", xml, re.S):
        cells = [_cell_text(c, shared)
                 for c in re.findall(r"<c[ >][^>]*?(?:/>|>.*?</c>)", row, re.S)]
        pairs.extend(row_pairs([c for c in cells if c]))

    return pairs


def _pdf_text(path: Path) -> str:
    """Raise ValueError on a broken PDF so read_document reports Unreadable
    without needing pypdf imported at module level."""
    from pypdf import PdfReader
    from pypdf.errors import PyPdfError

    try:
        return "\n".join(page.extract_text() or "" for page in PdfReader(path).pages[:MAX_PDF_PAGES])
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

        # "Consignee:" alone on its line is a label too, with its value beneath (#147 B3).
        bare = line.rstrip(":").strip()
        if is_pair or (not in_table and _is_label(bare)):
            if label is not None:
                pairs.append((label, CELL_SEPARATOR.join(collected)))
            label, collected = (None, []) if is_pair else (bare, [])
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
    return path.read_text(encoding="utf-8", errors="replace").split("\n", 1)[0].strip() or None


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
    except ImportError as error:
        log.warning("%s: no reader available (%s)", path.name, error)
        return None
    except UNREADABLE_ERRORS as error:
        log.warning("%s: no title could be read (%s)", path.name, error)
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
    except UNREADABLE_ERRORS as error:
        log.warning("%s: unreadable (%s)", path.name, error)
        return ParseStatusType.Unreadable, []

    if len(pairs) < MINIMUM_PAIRS:
        return ParseStatusType.Unreadable, pairs

    return ParseStatusType.Ok, pairs
