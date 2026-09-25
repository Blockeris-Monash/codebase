"""/process-email reads attachments from the dataset, or files this server saved itself - nothing else.

`resolve_attachment_path` returned any absolute path that existed, and `../` climbed out of
data/. Anyone could name a file on the server's disk - another person's Gmail attachment
under /tmp/shiphappens-mailbox, say - and get its seven fields back (#147 A2). The email id
was also joined into a cache path unchecked.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend import app as app_module
from backend.classify import ClassificationResult

DATASET_SI = app_module.DATA_DIR / "attachments" / "email_302_SI.xlsx"
SECRET_FIELDS = ("Shipper: SECRET CUSTOMER LTD\nConsignee: SECRET BUYER\n"
               "Notify Party: SECRET BUYER\nPort of Loading: PORT KLANG\nPort of Discharge: JEBEL ALI\n"
               "Container Count: 2 x 40HC\nGross Weight: 40,326 KG\n")


async def comparison(email) -> ClassificationResult:
    return ClassificationResult(email_id=email.email_id, category="BL_COMPARISON", decided_by="llm",
                                confidence=1.0, evidence="stub")


@pytest.fixture()
def client(monkeypatch) -> TestClient:
    monkeypatch.setattr(app_module, "classify", comparison)

    return TestClient(app_module.app)


def someone_elses_file(tmp_path: Path, role: str = "SI") -> str:
    # Named the way the route pairs attachments, {email_id}_{role}.
    path = tmp_path / f"email_999_{role}.txt"
    title = "SHIPPING INSTRUCTION" if role == "SI" else "BILL OF LADING"
    path.write_text(f"{title}\n{SECRET_FIELDS}", encoding="utf-8")

    return str(path)


def test_an_absolute_path_the_caller_names_is_not_read(tmp_path: Path) -> None:
    assert app_module.resolve_attachment_path(someone_elses_file(tmp_path)) is None


def test_a_path_that_climbs_out_of_the_dataset_is_not_read() -> None:
    assert app_module.resolve_attachment_path("../backend/app.py") is None


def test_a_file_this_request_saved_itself_is_read(tmp_path: Path) -> None:
    path = someone_elses_file(tmp_path)
    token = app_module.OWN_FILES.set(frozenset({path}))
    try:
        assert app_module.resolve_attachment_path(path) == Path(path)
    finally:
        app_module.OWN_FILES.reset(token)


def test_a_dataset_attachment_is_still_found_by_name() -> None:
    assert app_module.resolve_attachment_path("email_302_SI.xlsx") == DATASET_SI


def test_the_route_does_not_echo_another_files_fields(client: TestClient, tmp_path: Path) -> None:
    body = {"email_id": "email_999", "from_email": "a@b.com", "subject": "check", "body": "check",
            "attachments": [someone_elses_file(tmp_path), someone_elses_file(tmp_path, "BL")]}

    response = client.post("/process-email", json=body)

    assert response.status_code == 200
    assert response.json()["ComparisonResult"]["review_reason"] == "missing_attachment"
    assert "SECRET" not in response.text


@pytest.mark.parametrize("email_id", ["../../results/extracts/email_302", "a/b", "x" * 101])
def test_an_email_id_that_is_not_a_plain_name_reads_no_cache(email_id: str) -> None:
    assert app_module.load_saved_extract(email_id, "SI") is None
