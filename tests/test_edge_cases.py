"""Edge-case emails shaped like real customer mail (task 23, issue #71).

Each case in tests/edge_cases/ carries its expected result, written before it
was run. The emails go through the service's own path: compare_email (every
shipment in the email), run_pipeline, apply_cleaner, compare. Offline, the one stand-in is the model:
the repository's independent rules reader extracts the fields, so a result here
is the pipeline's and not a model's. The category of each email needs the model,
so that check is live only.

A case marked with known_gap is a finding: the test is an expected failure until
the gap is fixed, and strict, so fixing it without updating the case fails too.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from backend import app as app_module
from backend.classify import EmailInput, classify_email
from backend.extract.rules import fields_from_pairs
from tests.live_gate import needs_live

EDGE = Path(__file__).resolve().parent / "edge_cases"
CASES = json.loads((EDGE / "expected.json").read_text(encoding="utf-8"))
BY_CASE = {c["case"]: c["email_id"] for c in CASES}


def load_email(email_id: str) -> EmailInput:
    return EmailInput(**json.loads((EDGE / "inbox" / f"{email_id}.json").read_text(encoding="utf-8")))


def as_case(case: dict) -> pytest.param:
    marks = [pytest.mark.xfail(strict=True, reason=case["known_gap"])] if case["known_gap"] else []
    return pytest.param(case, id=case["case"], marks=marks)


class RulesReader:
    """Stands in for the model offline, with the same call the service makes."""

    def extract_fields(self, email_id: str, pairs: list[tuple[str, str]]) -> dict:
        return fields_from_pairs(pairs)


@pytest.fixture
def pipeline(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(app_module, "DATA_DIR", EDGE)
    monkeypatch.setattr(app_module, "extractor", RulesReader())

    def run(email_id: str) -> dict:
        report = asyncio.run(app_module.compare_email(load_email(email_id), live=False))
        return report.model_dump() if hasattr(report, "model_dump") else report

    return run


@pytest.mark.parametrize("case", [as_case(c) for c in CASES if c["expected"]])
def test_edge_case_reaches_the_expected_result(pipeline, case: dict) -> None:
    result, expected = pipeline(case["email_id"]), case["expected"]

    assert result["status"] == expected["status"], case["why"]
    if expected["review_reason"] is not None:
        assert result["review_reason"] == expected["review_reason"], case["why"]
    assert sorted(result["defect_fields"]) == sorted(expected["defect_fields"]), case["why"]


def test_edge_case_resent_gets_the_same_result(pipeline) -> None:
    first, again = pipeline(BY_CASE["edge_a4"]), pipeline(BY_CASE["edge_a10"])

    assert (first["status"], first["defect_fields"]) == (again["status"], again["defect_fields"])


def test_two_shipments_name_the_one_that_differs(pipeline) -> None:
    result = pipeline(BY_CASE["edge_a8"])

    assert result["evidence"].startswith("2 shipments in this email (shipment 1 OK, shipment 2 MISMATCH)")
    assert result["defect_fields"] == ["gross_weight_kg"]


def test_shipments_pair_files_by_the_rest_of_their_name() -> None:
    pair = lambda *names: app_module.shipments([f"attachments/{n}" for n in names])

    assert pair("e_SI.txt", "e_BL.txt") == [("attachments/e_SI.txt", "attachments/e_BL.txt")]
    assert pair("e_SI.txt", "e_BL.txt", "e_SI_2.pdf", "e_BL_2.xlsx") == [
        ("attachments/e_SI.txt", "attachments/e_BL.txt"), ("attachments/e_SI_2.pdf", "attachments/e_BL_2.xlsx")]
    # A revised BL has no SI of its own, and logos are not documents: still one shipment.
    assert len(pair("image001.png", "e_SI.txt", "e_BL.txt", "e_BL_REVISED.txt")) == 1
    assert pair("e_SI.txt") == [] and pair("notes.txt") == []


def test_every_edge_case_has_its_files_and_a_reason() -> None:
    for case in CASES:
        email = json.loads((EDGE / "inbox" / f"{case['email_id']}.json").read_text(encoding="utf-8"))
        assert case["why"].strip(), case["email_id"]
        for attachment in email["attachments"]:
            assert (EDGE / attachment).exists(), attachment


@needs_live("QWEN_API_KEY")
@pytest.mark.parametrize("case", [
    pytest.param(c, id=c["case"], marks=[pytest.mark.xfail(strict=True, reason=c["category_gap"])]
                 if c["category_gap"] else []) for c in CASES])
def test_edge_case_is_classified_as_expected(case: dict) -> None:
    result = asyncio.run(classify_email(load_email(case["email_id"])))

    assert result.category == case["category"], f"{case['why']} ({result.evidence})"


def test_a_mailbox_email_id_does_not_crash_the_comparison(pipeline) -> None:
    """The live mailbox (task 2) sends gmail_<Gmail message id>; the contract accepts it."""
    email = load_email(BY_CASE["edge_a4"]).model_dump(by_alias=True)
    gmail = EmailInput(**{**email, "email_id": "gmail_18c2f4e9a1b3d5f7"})

    report = asyncio.run(app_module.compare_email(gmail, live=False))

    assert report.status == "OK"
