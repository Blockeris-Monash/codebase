"""An SI request's drafted reply never fails the email, and never leaks where the PDF went (#147).

Found reviewing #145 and still on main after it merged:
- fpdf2's core fonts are Latin-1 only, so a curly quote (what Outlook types) or a dash in
  any field raised out of /process-email as a 500. In My mailbox two failures mark the
  email "could not be checked".
- The reply text ended "[SYSTEM NOTE: results/generated_bls/... was generated]", and that
  text fills the Send box, so one click emailed a server path to the customer.
- The reply said the PDF was attached; nothing can attach it.
- The email id became the file name, so "../x" wrote the PDF outside its folder.

And from the rest of the #145 review (#147 B1): the PDF is drawn in a bundled Unicode font
with fpdf2's current calls, and it is returned as bytes, never left on the server's disk.
"""
from __future__ import annotations

import io
import warnings
from pathlib import Path

import pytest
from pypdf import PdfReader
from fastapi.testclient import TestClient

from backend import app as app_module
from backend import si_request
from backend.classify import ClassificationResult, EmailInput
from backend.contracts import FIELD_NAMES


class Extractor:
    """Stands in for the model extractor with fixed fields, or a failure."""

    def __init__(self, container: str | None = "2 x 40HC") -> None:
        self.container = container

    def extract_fields(self, email_id: str, pairs: list) -> dict:
        if self.container is None:
            raise RuntimeError("model down")
        return {name: {"present": True, "label_seen": name,
                       "raw": self.container if name == "container_count" else "ACME LTD"}
                for name in FIELD_NAMES}


async def si_request_category(email) -> ClassificationResult:
    return ClassificationResult(email_id=email.email_id, category="SI_REQUEST", decided_by="llm",
                                confidence=1.0, evidence="stub")


@pytest.fixture()
def client(monkeypatch, tmp_path: Path) -> TestClient:
    monkeypatch.setattr(app_module, "classify", si_request_category)
    monkeypatch.chdir(tmp_path)   # anything written relative to the working directory lands here

    return TestClient(app_module.app)


EMAIL = EmailInput(email_id="email_022", from_email="a@b.com", subject="SI", body="SI below", attachments=[])


def post(client: TestClient, email_id: str = "email_022"):
    return client.post("/process-email", json={"email_id": email_id, "from_email": "a@b.com",
                                               "subject": "SI", "body": "SI below", "attachments": []})


@pytest.mark.parametrize("container", ["2 x 40’HC", "2 – 40HC", "上海 2 x 40HC"])
def test_a_character_the_pdf_font_lacks_still_drafts(client, monkeypatch, container: str) -> None:
    monkeypatch.setattr(si_request, "extractor", Extractor(container))

    response = post(client)

    assert response.status_code == 200
    assert response.json()["draft_reply"]


def test_the_reply_names_no_server_path_and_claims_no_attachment(client, monkeypatch) -> None:
    monkeypatch.setattr(si_request, "extractor", Extractor())

    reply = post(client).json()["draft_reply"]

    assert "SYSTEM NOTE" not in reply
    assert "generated_bls" not in reply
    assert "attached" not in reply.lower()


def test_a_failed_draft_leaves_the_email_classified(client, monkeypatch) -> None:
    monkeypatch.setattr(si_request, "extractor", Extractor(None))

    response = post(client)

    assert response.status_code == 200
    assert response.json()["draft_reply"] is None
    assert response.json()["ClassificationResult"]["category"] == "SI_REQUEST"


def pdf_text(pdf: bytes) -> str:
    return "".join(page.extract_text() for page in PdfReader(io.BytesIO(pdf)).pages)


def test_a_complete_si_gives_a_pdf_and_nothing_on_disk(tmp_path: Path, monkeypatch) -> None:
    """The folder was made at import, relative to wherever the server started, and
    nothing ever read or deleted what went into it."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(si_request, "extractor", Extractor())

    _reply, pdf, _fields = si_request.process_si_request(EMAIL)

    assert pdf.startswith(b"%PDF")
    assert list(tmp_path.iterdir()) == []


def test_a_missing_field_asks_for_it_and_makes_no_pdf(monkeypatch) -> None:
    class NoWeight(Extractor):
        def extract_fields(self, email_id: str, pairs: list) -> dict:
            return {**super().extract_fields(email_id, pairs),
                    "gross_weight_kg": {"present": False, "label_seen": None, "raw": None}}

    monkeypatch.setattr(si_request, "extractor", NoWeight())

    reply, pdf, _fields = si_request.process_si_request(EMAIL)

    assert "Gross Weight Kg" in reply
    assert pdf is None


def test_curly_quotes_dashes_and_accents_are_drawn_as_written() -> None:
    """Latin-1 core fonts turned these into '?' or plain punctuation in the PDF."""
    fields = Extractor("2 x 40’HC – Société Générale").extract_fields("email_022", [])

    text = pdf_text(si_request.generate_pdf(fields))

    assert "40’HC – Société Générale" in text


def test_the_pdf_uses_no_call_fpdf2_has_deprecated() -> None:
    """Arial, txt= and ln=True all warn today and break on a future fpdf2."""
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        si_request.generate_pdf(Extractor().extract_fields("email_022", []))
