"""Edge-case emails shaped like real customer mail (task 23, issue #71).

Each case in tests/edge_cases/ carries its expected result, written before it
was run. The emails go through the service's own path: read_paired_attachments,
run_pipeline, apply_cleaner, compare. Offline, the one stand-in is the model:
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
from pydantic import ValidationError

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
        paired = app_module.read_paired_attachments(load_email(email_id))
        report = asyncio.run(app_module.run_pipeline(paired, live=False))
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


@pytest.mark.xfail(strict=True, raises=ValidationError,
                   reason="The contracts accept only email_NNN ids, so a Gmail message id crashes compare(). "
                          "The live mailbox (task 2) must map its ids or the contract must widen.")
def test_a_mailbox_email_id_does_not_crash_the_comparison(pipeline) -> None:
    email = load_email(BY_CASE["edge_a4"]).model_dump(by_alias=True)
    gmail = EmailInput(**{**email, "email_id": "18c2f4e9a1b3d5f7"})

    paired = app_module.read_paired_attachments(gmail)
    report = asyncio.run(app_module.run_pipeline(paired, live=False))

    assert report.status == "OK"
