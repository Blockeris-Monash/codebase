"""The contracts' if-and-only-if rules are enforced, not just described (#147 B3).

Contracts 04 and 05 said in prose that review_reason is set exactly when the status is
NEEDS_REVIEW, that defect_fields is non-empty exactly when it is MISMATCH, and that
has_defect is true exactly then. Nothing checked any of it, so a record could break
the scorer's assumptions and still PASS.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.compare.comparator import ComparisonResult
from cli.validate_contracts import load_contract, validate

OK = {"email_id": "email_001", "status": "OK", "review_reason": None, "rows": [], "defect_fields": [],
      "evidence": "All 7 fields match."}
MISMATCH = {**OK, "status": "MISMATCH", "defect_fields": ["shipper"]}
REVIEW = {**OK, "status": "NEEDS_REVIEW", "review_reason": "missing_value"}

BROKEN_COMPARISONS = [
    pytest.param({**OK, "review_reason": "missing_value"}, "review_reason", id="reason-without-review"),
    pytest.param({**REVIEW, "review_reason": None}, "review_reason", id="review-without-reason"),
    pytest.param({**MISMATCH, "defect_fields": []}, "defect_fields", id="mismatch-without-fields"),
    pytest.param({**OK, "defect_fields": ["shipper"]}, "defect_fields", id="fields-without-mismatch"),
]


def entry(comparison: dict, **changes: object) -> dict:
    fields = {key: comparison[key] for key in ("status", "review_reason", "defect_fields")}
    return {"category": "BL_COMPARISON", **fields, "has_defect": comparison["status"] == "MISMATCH", **changes}


def errors_for(record: dict, contract: str) -> list[str]:
    return validate(record, load_contract(contract), contract, [])


@pytest.mark.parametrize("record", [OK, MISMATCH, REVIEW], ids=["ok", "mismatch", "review"])
def test_a_consistent_record_passes_both_contracts(record: dict) -> None:
    assert errors_for(record, "ComparisonResult") == []
    assert errors_for(entry(record), "SubmissionEntry") == []


@pytest.mark.parametrize("record, rule", BROKEN_COMPARISONS)
def test_a_broken_rule_is_reported_by_name(record: dict, rule: str) -> None:
    for contract, value in (("ComparisonResult", record), ("SubmissionEntry", entry(record))):
        found = errors_for(value, contract)

        assert len(found) == 1 and rule in found[0] and "if and only if" in found[0], (contract, found)


@pytest.mark.parametrize("record, has_defect", [(OK, True), (MISMATCH, False)], ids=["ok-flagged", "mismatch-unflagged"])
def test_has_defect_must_follow_the_status(record: dict, has_defect: bool) -> None:
    found = errors_for(entry(record, has_defect=has_defect), "SubmissionEntry")

    assert len(found) == 1 and "has_defect" in found[0]


@pytest.mark.parametrize("record, _rule", BROKEN_COMPARISONS)
def test_the_service_cannot_build_a_result_that_breaks_its_own_contract(record: dict, _rule: str) -> None:
    with pytest.raises(ValidationError):
        ComparisonResult(**record)
