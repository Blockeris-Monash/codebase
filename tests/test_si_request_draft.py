"""An SI request's drafted reply never fails the email, and never leaks where the PDF went (#147).

Found reviewing #145 and still on main after it merged:
- fpdf2's core fonts are Latin-1 only, so a curly quote (what Outlook types) or a dash in
  any field raised out of /process-email as a 500. In My mailbox two failures mark the
  email "could not be checked".
- The reply text ended "[SYSTEM NOTE: results/generated_bls/... was generated]", and that
  text fills the Send box, so one click emailed a server path to the customer.
- The reply said the PDF was attached; nothing can attach it.
- The email id became the file name, so "../x" wrote the PDF outside its folder.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend import app as app_module
from backend import si_request
from backend.classify import ClassificationResult
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
    monkeypatch.setattr(si_request, "RESULTS_DIR", tmp_path)

    return TestClient(app_module.app)


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


@pytest.mark.parametrize("email_id", ["../../escape", "/tmp/escape", "a/b/c"])
def test_the_pdf_stays_in_its_folder(tmp_path: Path, monkeypatch, email_id: str) -> None:
    monkeypatch.setattr(si_request, "RESULTS_DIR", tmp_path)

    written = Path(si_request.generate_pdf(Extractor().extract_fields(email_id, []), email_id))

    assert written.parent == tmp_path
