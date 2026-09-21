"""Batch runner: the model is faked, so these run offline."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.extract.batch import extract_attachment, run_batch
from backend.contracts import FIELD_NAMES

SI_TEXT = "SHIPPING INSTRUCTION\n=====\nShipper: ACME LTD\nLoad Port: SINGAPORE\nPOD: KARACHI\n"


class FakeExtractor:
    def __init__(self, answer: bool = True) -> None:
        self.answer, self.calls = answer, []

    def extract_fields(self, email_id, pairs):
        self.calls.append(email_id)
        if not self.answer:
            return None
        return {f: {"present": True, "label_seen": f, "raw": "X"} for f in FIELD_NAMES}


@pytest.fixture
def attachments(tmp_path: Path) -> Path:
    folder = tmp_path / "attachments"
    folder.mkdir()
    (folder / "email_001_SI.txt").write_text(SI_TEXT)
    (folder / "email_001_BL.txt").write_text(SI_TEXT.replace("SHIPPING INSTRUCTION", "BILL OF LADING"))
    (folder / "email_002_SI.txt").write_text("nothing readable here")
    (folder / "notes.txt").write_text("not an SI or BL")
    return folder


def test_extract_attachment_builds_a_document_extract(attachments: Path) -> None:
    result = extract_attachment(attachments / "email_001_SI.txt", FakeExtractor())

    assert result["email_id"] == "email_001"
    assert result["declared_role"] == "SI"
    assert result["format"] == "txt"
    assert result["source_path"] == "attachments/email_001_SI.txt"
    assert result["parse_status"] == "ok"
    assert set(result["fields"]) == set(FIELD_NAMES)


def test_unreadable_attachment_skips_the_model_and_is_flagged(attachments: Path) -> None:
    extractor = FakeExtractor()
    result = extract_attachment(attachments / "email_002_SI.txt", extractor)

    assert result["parse_status"] == "unreadable"
    assert extractor.calls == []
    assert all(not f["present"] for f in result["fields"].values())


def test_model_that_never_answers_gives_none(attachments: Path) -> None:
    assert extract_attachment(attachments / "email_001_SI.txt", FakeExtractor(answer=False)) is None


def test_run_batch_writes_one_json_per_si_or_bl(attachments: Path, tmp_path: Path) -> None:
    out = tmp_path / "out"
    summary = run_batch(attachments, out, FakeExtractor())

    assert sorted(p.name for p in out.glob("*.json")) == [
        "email_001_BL.json", "email_001_SI.json", "email_002_SI.json"]
    assert json.loads((out / "email_001_SI.json").read_text())["parse_status"] == "ok"
    assert summary == {"done": 3, "skipped": 0, "failed": []}


def test_a_rerun_skips_saved_results_and_retries_failures(attachments: Path, tmp_path: Path) -> None:
    out = tmp_path / "out"
    run_batch(attachments, out, FakeExtractor(answer=False))
    assert list(out.glob("*.json")) == [out / "email_002_SI.json"]  # only the unreadable one is saved

    extractor = FakeExtractor()
    summary = run_batch(attachments, out, extractor)

    assert summary["failed"] == [] and summary["skipped"] == 1 and summary["done"] == 2
    assert sorted(extractor.calls) == ["email_001", "email_001"]


def test_workers_run_documents_at_the_same_time_and_save_the_same_results(
        attachments: Path, tmp_path: Path) -> None:
    import threading
    import time

    class Slow(FakeExtractor):
        def __init__(self) -> None:
            super().__init__()
            self.running = self.peak = 0
            self.lock = threading.Lock()

        def extract_fields(self, email_id, pairs):
            with self.lock:
                self.running += 1
                self.peak = max(self.peak, self.running)
            time.sleep(0.2)
            with self.lock:
                self.running -= 1
            return super().extract_fields(email_id, pairs)

    extractor = Slow()
    summary = run_batch(attachments, tmp_path / "out", extractor, workers=2)

    assert extractor.peak == 2
    assert summary == {"done": 3, "skipped": 0, "failed": []}
    assert len(list((tmp_path / "out").glob("*.json"))) == 3
