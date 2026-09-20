"""Lane A — every attachment format reaches the same labelled pairs."""
from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from contract_types import FIELD_NAMES, ParseStatusType
from make_fixtures import canonical_field, detect_doc_type
from read_documents import READERS, document_title, read_document

# Measured over the provided dataset. A change here means the data changed
# or a reader regressed - both worth failing on.
TOTAL_ATTACHMENTS = 250
EXPECTED_STATUS_COUNTS = {"txt": 192, "docx": 8, "xlsx": 22, "pdf": 28}
MINIMUM_PAIRS = 3


def labelled_fields(path: Path) -> dict[str, str]:
    """Run a document through read + label alignment, as the pipeline does."""
    _, pairs = read_document(path)
    found: dict[str, str] = {}
    for label, value in pairs:
        field = canonical_field(label)
        if field is not None and field not in found:
            found[field] = value

    return found


# --- every format parses ------------------------------------------------

@pytest.mark.parametrize("filename", [
    "email_064_SI.txt",
    "email_055_SI.xlsx",
    "email_055_BL.docx",
])
def test_reads_every_supported_format(attachments: Path, filename: str) -> None:
    status, pairs = read_document(attachments / filename)

    assert status == ParseStatusType.Ok
    assert len(pairs) >= MINIMUM_PAIRS


@pytest.mark.parametrize("filename", [
    "email_064_SI.txt",
    "email_055_SI.xlsx",
    "email_055_BL.docx",
])
def test_locates_all_seven_fields_in_every_format(attachments: Path, filename: str) -> None:
    found = labelled_fields(attachments / filename)

    assert sorted(found) == sorted(FIELD_NAMES)


# --- failure modes ------------------------------------------------------

def test_absent_file_reports_missing(tmp_path: Path) -> None:
    status, pairs = read_document(tmp_path / "nothing_here.txt")

    assert status == ParseStatusType.Missing
    assert pairs == []


def test_unsupported_extension_reports_not_attempted(tmp_path: Path) -> None:
    unsupported = tmp_path / "scan.tiff"
    unsupported.write_bytes(b"\x00\x01")

    status, _ = read_document(unsupported)

    assert status == ParseStatusType.NotAttempted


def test_corrupt_office_file_reports_unreadable(tmp_path: Path) -> None:
    """A .docx that is not a ZIP must escalate, not raise."""
    corrupt = tmp_path / "broken.docx"
    corrupt.write_bytes(b"%PDF-1.5 not actually a word document")

    status, _ = read_document(corrupt)

    assert status == ParseStatusType.Unreadable


def test_near_empty_document_reports_unreadable(tmp_path: Path) -> None:
    """Too few pairs to be a real document - treat as unreadable rather than
    handing an almost-empty record downstream."""
    sparse = tmp_path / "sparse.txt"
    sparse.write_text("BILL OF LADING (DRAFT)\nShipper: ACME\n")

    status, _ = read_document(sparse)

    assert status == ParseStatusType.Unreadable


def test_no_attachment_in_the_corpus_raises(attachments: Path) -> None:
    """Whatever the file, read_document returns a status - never an exception."""
    statuses = [read_document(p)[0] for p in sorted(attachments.iterdir())]

    assert len(statuses) == TOTAL_ATTACHMENTS


# --- Word specifics -----------------------------------------------------

def test_word_line_breaks_separate_name_from_address(attachments: Path) -> None:
    """Word puts a party block's lines in one paragraph split by <w:br/>.
    Without handling that, the name and address run together and the
    name-only comparison silently fails."""
    found = labelled_fields(attachments / "email_055_BL.docx")

    assert found["shipper"].startswith("APRIL FINE PAPER TRADING | ")


def test_word_matches_excel_segment_layout(attachments: Path) -> None:
    """Both formats must present a party the same way, or the name-only
    split works on one and not the other."""
    from_excel = labelled_fields(attachments / "email_055_SI.xlsx")
    from_word = labelled_fields(attachments / "email_055_BL.docx")

    assert from_excel["consignee"].split(" | ")[0] == from_word["consignee"].split(" | ")[0]


# --- Excel specifics ----------------------------------------------------

def test_excel_resolves_shared_strings(attachments: Path) -> None:
    """Excel stores most text in a shared table referenced by index. An
    unresolved reference would surface as a bare integer."""
    found = labelled_fields(attachments / "email_055_SI.xlsx")

    assert not found["consignee"].isdigit()


def test_xml_entities_are_unescaped(attachments: Path) -> None:
    """&amp; surviving the parse would make BALL & DOGGETT mismatch itself
    across formats."""
    found = labelled_fields(attachments / "email_005_SI.xlsx")

    assert "&amp;" not in found["consignee"]


# --- label alignment ----------------------------------------------------

@pytest.mark.parametrize("label,expected", [
    ("Shipper/Exporter", "shipper"),               # slash variant
    ("To the Order of", "consignee"),              # different words entirely
    ("Load Port", "port_of_loading"),              # the brief's own example
    ("No. of Containers or Packages", "container_count"),
    ("Gross Wt (kgs)", "gross_weight_kg"),         # parenthetical unit
])
def test_label_variants_align_by_meaning(label: str, expected: str) -> None:
    assert canonical_field(label) == expected


@pytest.mark.parametrize("label,expected", [
    ("Gross Weight毛重(KGS)", "gross_weight_kg"),      # .txt, no space
    ("Gross Wt (kgs) (毛重 KGS)", "gross_weight_kg"),  # .docx, two brackets
])
def test_cjk_in_a_label_does_not_block_alignment(label: str, expected: str) -> None:
    """CJK appears in labels across .txt and .docx, never in values."""
    assert canonical_field(label) == expected


@pytest.mark.parametrize("label", ["NET WEIGHT", "Vessel"])
def test_unrelated_labels_are_not_claimed(label: str) -> None:
    """NET WEIGHT sits beside GROSS in the SI as a decoy."""
    assert canonical_field(label) is None


# --- document type is read from the header, not the filename ------------

@pytest.mark.parametrize("filename,expected", [
    ("email_064_SI.txt", "SI"),
    ("email_064_BL.txt", "BL"),
    ("email_501_BL.txt", "COMMERCIAL INVOICE"),
    ("email_502_BL.txt", "PACKING LIST"),
    ("email_503_BL.txt", "CERTIFICATE OF ORIGIN"),
])
def test_document_type_comes_from_the_header(attachments: Path,
                                             filename: str, expected: str) -> None:
    """Emails 501-505 attach an invoice, packing list or certificate under a
    _BL filename. Trusting the name produces a confident wrong answer."""
    header = detect_doc_type((attachments / filename).read_text(errors="replace"))

    assert header == expected


# --- the whole corpus ---------------------------------------------------

UNREADABLE_ATTACHMENTS = 8      # 6 scanned image-only PDFs + 2 corrupt PDFs


def test_every_attachment_reads_except_the_genuinely_unreadable(attachments: Path) -> None:
    """242 of 250 parse, across all four formats. The 8 that do not are 6
    scanned image-only PDFs needing OCR and 2 corrupt files."""
    readable = [p for p in attachments.iterdir()
                if read_document(p)[0] == ParseStatusType.Ok]

    assert len(readable) == TOTAL_ATTACHMENTS - UNREADABLE_ATTACHMENTS


def test_a_document_we_cannot_parse_says_so(attachments: Path) -> None:
    """A scanned or corrupt PDF must report Unreadable. Returning the couple
    of accidental pairs it can find would make the pipeline claim the fields
    are MISSING, which is a different and false statement."""
    statuses = {read_document(p)[0] for p in attachments.glob("*.pdf")}

    assert statuses == {ParseStatusType.Ok, ParseStatusType.Unreadable}


@pytest.mark.parametrize("filename", ["email_059_SI.pdf", "email_059_BL.pdf",
                                      "email_160_SI.pdf"])
def test_pdf_form_layout_yields_all_seven_fields(attachments: Path, filename: str) -> None:
    """The PDFs put a label on its own line above its value, and restate the
    totals below the container table as "label: value". Both shapes have to
    land."""
    found = labelled_fields(attachments / filename)

    assert sorted(found) == sorted(FIELD_NAMES)



# --- one dispatch table, so a format cannot be half-supported -----------

SAMPLE_PER_FORMAT = {
    "txt": "email_064_SI.txt",
    "docx": "email_055_BL.docx",
    "xlsx": "email_055_SI.xlsx",
    "pdf": "email_059_SI.pdf",
}
# Formats with no example in the dataset, covered by their own test module.
TESTED_ELSEWHERE = {"edi"}


def test_every_format_in_the_table_has_a_sample_to_test() -> None:
    """If someone adds a format, this fails until they add a sample here -
    which is the prompt to test it rather than assume it works."""
    assert set(READERS) == set(SAMPLE_PER_FORMAT) | TESTED_ELSEWHERE


@pytest.mark.parametrize("fmt,filename", sorted(SAMPLE_PER_FORMAT.items()))
def test_every_format_yields_both_pairs_and_a_title(attachments: Path, fmt: str,
                                                    filename: str) -> None:
    """Reading a document and reading its title used to be two separate
    dispatch points that could drift. One Reader entry now supplies both, and
    this checks neither half is missing."""
    status, pairs = read_document(attachments / filename)

    assert status == ParseStatusType.Ok
    assert pairs
    assert document_title(attachments / filename)


def test_an_unreadable_document_has_no_title_rather_than_raising(tmp_path: Path) -> None:
    """document_title runs on files that may not parse, so it must fail the
    same way read_document does - by returning nothing."""
    corrupt = tmp_path / "broken.xlsx"
    corrupt.write_bytes(b"not a zip at all")

    assert document_title(corrupt) is None
