"""The orchestrator endpoint, over real attachments, on the cached path.

Was a print-only script under `if __name__ == "__main__"`, so pytest
collected nothing from it and the endpoint went unguarded. The three cases
and their expected verdicts are the ones the script documented.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from tests.live_gate import needs_live
from fastapi.testclient import TestClient

from backend.app import app, load_saved_extract
from backend.read.documents import document_title, read_document

CACHED = "/extract-clean-compare?live=false"
LIVE = "/extract-clean-compare?live=true"
FIELD_COUNT = 7

client = TestClient(app)


def compare_pair(attachments: Path, url: str,
                 email_id: str, si_file: str, bl_file: str) -> dict:
    """Read both attachments the way the reader stage does, then POST them.

    The title and the parse status travel with the pairs: the endpoint
    cannot recover either from the pairs alone, and the comparator escalates
    a document whose type or parse status it does not know.
    """
    si_path, bl_path = attachments / si_file, attachments / bl_file
    si_status, si_pairs = read_document(si_path)
    bl_status, bl_pairs = read_document(bl_path)

    response = client.post(url, json={
        "email_id": email_id,
        "si_pairs": si_pairs,
        "bl_pairs": bl_pairs,
        "si_title": document_title(si_path),
        "bl_title": document_title(bl_path),
        "si_parse_status": si_status,
        "bl_parse_status": bl_status,
    })

    assert response.status_code == 200, response.text

    return response.json()


def test_cached_pair_reports_both_seeded_defects(attachments: Path) -> None:
    report = compare_pair(attachments, CACHED,
                          "email_025", "email_025_SI.txt", "email_025_BL.txt")

    assert report["status"] == "MISMATCH"
    assert report["review_reason"] is None
    assert report["defect_fields"] == ["port_of_discharge", "container_count"]


def test_cached_clean_pair_is_ok(attachments: Path) -> None:
    report = compare_pair(attachments, CACHED,
                          "email_064", "email_064_SI.txt", "email_064_BL.txt")

    assert report["status"] == "OK"
    assert report["defect_fields"] == []


def test_excel_si_against_word_bl_is_ok(attachments: Path) -> None:
    """Different formats on the two sides still align field for field."""
    report = compare_pair(attachments, CACHED,
                          "email_055", "email_055_SI.xlsx", "email_055_BL.docx")

    assert report["status"] == "OK"
    assert report["defect_fields"] == []


def test_every_field_is_reported(attachments: Path) -> None:
    """All seven rows come back even when they all match, because the review
    screen shows the comparison, not just the defects."""
    report = compare_pair(attachments, CACHED,
                          "email_064", "email_064_SI.txt", "email_064_BL.txt")

    assert len(report["rows"]) == FIELD_COUNT
    assert all(row["verdict"] == "match" for row in report["rows"])


def test_cache_carries_the_parse_metadata() -> None:
    """Regression guard. The loader used to return `fields` alone, so every
    document reached the comparator with no parse_status and no detected
    type, and all 520 emails came back NEEDS_REVIEW/unreadable."""
    extract = load_saved_extract("email_025", "SI")

    assert extract is not None
    assert extract["parse_status"] == "ok"
    assert extract["detected_doc_type"] == "SI"
    assert "fields" in extract


@needs_live("QWEN_API_KEY")
def test_live_model_path_reaches_the_same_verdict(attachments: Path) -> None:
    """Same pair, cache bypassed. Slow, and it spends quota."""
    report = compare_pair(attachments, LIVE,
                          "email_025", "email_025_SI.txt", "email_025_BL.txt")

    assert report["status"] == "MISMATCH"
    assert report["defect_fields"] == ["port_of_discharge", "container_count"]
