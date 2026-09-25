"""A Word or Excel file that inflates to gigabytes is refused, not read into memory (#147 A2).

A .docx or .xlsx is a ZIP. The 5 MB upload limit counts compressed bytes, so a few MB of
zeros inflate to gigabytes and the service is killed. It could be reached two ways: through
/check-files with no sign-in, or by emailing the file to anyone signed in to My mailbox.
"""
from __future__ import annotations

import base64
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from pypdf._page import PageObject

from backend import app as app_module
from backend.contracts import ParseStatusType
from backend.read import documents
from backend.read.documents import MAX_MEMBER_BYTES, MAX_PDF_PAGES, document_title, read_document

INFLATED = MAX_MEMBER_BYTES + 1
# Two dataset documents that read as Ok, so without the cap the padded copies read as Ok too.
DOCX = "email_055_BL.docx"
XLSX = "email_005_BL.xlsx"
ATTACHMENTS = Path(__file__).resolve().parents[1] / "data" / "attachments"


class Recorder:
    """Stands in for the model extractor and records every call."""

    def __init__(self, calls: list[str]) -> None:
        self.calls = calls

    def extract_fields(self, email_id: str, pairs: list) -> None:
        self.calls.append(email_id)


def bomb(path: Path, source: str, member: str) -> Path:
    """A real dataset document with its main XML part padded past the cap. It reads
    as a normal SI without the cap, so the test fails unless the cap is enforced."""
    with zipfile.ZipFile(ATTACHMENTS / source) as original, \
            zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as padded:
        for info in original.infolist():
            data = original.read(info.filename)
            if info.filename == member:
                data += b"<!--" + b"0" * INFLATED + b"-->"
            padded.writestr(info.filename, data)

    return path


@pytest.mark.parametrize(("source", "member"), [
    (DOCX, "word/document.xml"),
    (XLSX, "xl/worksheets/sheet1.xml"),
])
def test_an_inflating_member_is_unreadable(tmp_path: Path, source: str, member: str) -> None:
    status, pairs = read_document(bomb(tmp_path / source, source, member))

    assert status == ParseStatusType.Unreadable
    assert pairs == []


def test_an_inflating_member_has_no_title(tmp_path: Path) -> None:
    assert document_title(bomb(tmp_path / DOCX, DOCX, "word/document.xml")) is None


def test_a_header_that_understates_the_size_is_still_refused(tmp_path: Path) -> None:
    path = bomb(tmp_path / DOCX, DOCX, "word/document.xml")
    raw = bytearray(path.read_bytes())
    name = b"word/document.xml"
    # Rewrite the uncompressed size of that member, in both of its headers, to 100 bytes.
    for signature, offset in ((b"PK\x03\x04", 22), (b"PK\x01\x02", 24)):
        at = next(i for i in _all(raw, signature) if name in raw[i:i + 64])
        raw[at + offset:at + offset + 4] = (100).to_bytes(4, "little")
    path.write_bytes(bytes(raw))

    status, _ = read_document(path)

    assert status == ParseStatusType.Unreadable


def test_the_upload_route_answers_needs_review_for_a_bomb(tmp_path: Path, monkeypatch) -> None:
    data = base64.b64encode(bomb(tmp_path / DOCX, DOCX, "word/document.xml").read_bytes()).decode()
    body = {"si": {"name": "si.docx", "data": data}, "bl": {"name": "bl.docx", "data": data}}

    calls: list[str] = []
    monkeypatch.setattr(app_module, "extractor", Recorder(calls))

    response = TestClient(app_module.app).post("/check-files", json=body)

    assert response.status_code == 200
    assert response.json()["review_reason"] == "unreadable"
    assert calls == [], "a file with nothing read from it must not reach the model"


def test_a_long_pdf_is_read_only_to_the_page_cap(tmp_path: Path, monkeypatch) -> None:
    writer = PdfWriter()
    for _ in range(MAX_PDF_PAGES + 10):
        writer.add_blank_page(width=100, height=100)
    path = tmp_path / "long.pdf"
    with path.open("wb") as handle:
        writer.write(handle)
    calls: list[int] = []
    monkeypatch.setattr(PageObject, "extract_text", lambda self, *a, **k: calls.append(1) or "")

    documents._pdf_text(path)

    assert len(calls) == MAX_PDF_PAGES


def _all(raw: bytearray, signature: bytes) -> list[int]:
    found, at = [], raw.find(signature)
    while at >= 0:
        found.append(at)
        at = raw.find(signature, at + 1)

    return found


def test_the_padded_document_reads_normally_below_the_cap(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(documents, "MAX_MEMBER_BYTES", INFLATED * 2)

    status, _ = read_document(bomb(tmp_path / DOCX, DOCX, "word/document.xml"))

    assert status == ParseStatusType.Ok


def test_real_documents_are_well_under_the_cap() -> None:
    root = ATTACHMENTS
    sizes = [info.file_size for path in [*root.glob("*.docx"), *root.glob("*.xlsx")]
             for info in zipfile.ZipFile(path).infolist()]

    assert max(sizes) < MAX_MEMBER_BYTES // 10
