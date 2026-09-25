"""Check an SI and a draft BL someone uploads, without signing in (Meeting 7, job 10).

The same reading, extraction and comparison as a Gmail attachment. Offline: the
repository's rules reader stands in for the model, so a result here is the pipeline's.
"""
from __future__ import annotations

import base64
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend import app as app_module
from backend import middleware
from backend.extract.rules import fields_from_pairs

EDGE = Path(__file__).resolve().parent / "edge_cases" / "attachments"
SI = (EDGE / "email_901_SI.txt").read_bytes()
BL = (EDGE / "email_901_BL.txt").read_bytes()
BL_WRONG_WEIGHT = BL.replace(b"21,577", b"21,977")
FRONTEND = Path(__file__).resolve().parents[1] / "frontend"


class RulesReader:
    def extract_fields(self, email_id: str, pairs: list[tuple[str, str]]) -> dict:
        return fields_from_pairs(pairs)


def file(name: str, data: bytes) -> dict:
    return {"name": name, "data": base64.b64encode(data).decode()}


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setattr(app_module, "extractor", RulesReader())
    monkeypatch.setattr(app_module, "UPLOAD_DIR", tmp_path)
    with TestClient(app_module.app) as client:
        client.upload_dir = tmp_path
        yield client


def test_two_uploaded_files_are_checked_without_signing_in(client) -> None:
    got = client.post("/check-files", json={"si": file("instruction.txt", SI), "bl": file("draft.txt", BL_WRONG_WEIGHT)})

    assert got.status_code == 200, got.text
    checked = got.json()
    assert checked["id"].startswith("upload_") and checked["uploaded"] is True
    assert checked["category"] == "BL_COMPARISON"
    assert checked["status"] == "MISMATCH" and checked["defect_fields"] == ["gross_weight_kg"]
    assert set(checked["docs"]) == {"SI", "BL"} and checked["docs"]["SI"]["pairs"]
    assert checked["subject"] == "instruction.txt and draft.txt"


def test_matching_files_are_verified(client) -> None:
    got = client.post("/check-files", json={"si": file("si.txt", SI), "bl": file("bl.txt", BL)})

    assert got.status_code == 200, got.text
    assert got.json()["status"] == "OK"


def test_nothing_uploaded_is_kept_on_the_server(client) -> None:
    client.post("/check-files", json={"si": file("si.txt", SI), "bl": file("bl.txt", BL)})

    assert list(client.upload_dir.iterdir()) == []


def test_the_uploaders_file_name_is_never_used_as_a_path(client) -> None:
    got = client.post("/check-files", json={"si": file("../../escape.txt", SI), "bl": file("/etc/bl.txt", BL)})

    assert got.status_code == 200, got.text
    assert not (client.upload_dir.parent.parent / "escape.txt").exists()
    assert ".." not in got.json()["docs"]["SI"]["name"]


@pytest.mark.parametrize("name", ["virus.exe", "photo.png", "no-extension"])
def test_a_file_type_the_reader_cannot_open_is_refused(client, name: str) -> None:
    got = client.post("/check-files", json={"si": file(name, SI), "bl": file("bl.txt", BL)})

    assert got.status_code == 415
    assert "txt" in got.json()["detail"]


def test_a_file_that_is_too_big_is_refused(client, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app_module, "UPLOAD_MAX_BYTES", 100)

    got = client.post("/check-files", json={"si": file("si.txt", SI), "bl": file("bl.txt", BL)})

    assert got.status_code == 413


def test_a_file_that_is_not_base64_is_refused(client) -> None:
    got = client.post("/check-files", json={"si": {"name": "si.txt", "data": "not base64!!"}, "bl": file("bl.txt", BL)})

    assert got.status_code == 400


def test_checking_uploads_counts_against_the_model_rate_limit() -> None:
    assert "/check-files" in middleware.LIMITED_PATHS


# ---------------------------------------------------------------- the page

PAGE = (FRONTEND / "index.html").read_text(encoding="utf-8")


def test_the_landing_page_upload_option_is_no_longer_planned() -> None:
    card = PAGE[PAGE.index('t("Upload SI and BL files")') - 200:PAGE.index('t("Upload SI and BL files")') + 400]
    assert 'class="opt off' not in card and 't("Planned")' not in card
    assert 'data-a="upload"' in card


def test_the_upload_dialog_asks_for_an_si_and_a_bl() -> None:
    dialog = PAGE[PAGE.index("function uploadHTML"):]
    dialog = dialog[:dialog.index("\n}\n")]
    assert 'data-up="${role}"' in dialog and 'pick("SI"' in dialog and 'pick("BL"' in dialog
    assert 'accept=".txt,.docx,.xlsx,.pdf,.edi"' in dialog


def test_the_upload_goes_to_the_backend_without_a_sign_in() -> None:
    send = PAGE[PAGE.index("async function checkFiles"):]
    send = send[:send.index("\n}\n")]
    assert 'API_BASE + "/check-files"' in send
    assert "Authorization" not in send


def test_uploads_have_their_own_mailbox() -> None:
    assert 'S.mailbox==="upload" ? S.uploads' in PAGE
    menu = PAGE[PAGE.index("function accountHTML"):]
    menu = menu[:menu.index("\n}\n")]
    assert '"uploadsbox"' in menu and 't("Manual uploads")' in menu


def test_the_uploads_mailbox_offers_to_upload_more() -> None:
    assert '${S.mailbox==="upload"?`<button class="btn alt" data-a="upload">${ICON.UPLOAD}${t("Upload more")}</button>`:""}' in PAGE
