"""The full submission file: one entry per email, all 520 ids (#162 A3).

The brief: "one JSON object keyed by email_id, following the format in sample_submission.json.
Include every email." Contract 5 says all 520 ids must be present. Nothing wrote it: the
scorer's file was built by hand, and /process-email answers one email at a time. It is now
written from the saved results, so it always agrees with what the page shows.
"""
from __future__ import annotations

import json
from pathlib import Path

from cli.make_submission import build, main
from cli.validate_contracts import load_contract, validate

ROOT = Path(__file__).resolve().parents[1]


def saved_results() -> list[dict]:
    src = (ROOT / "frontend" / "results.js").read_text(encoding="utf-8")
    return json.loads(src[src.index("["): src.rindex("]") + 1])


def test_every_email_in_the_inbox_has_an_entry() -> None:
    submission = build(saved_results())
    inbox = {p.stem for p in (ROOT / "data" / "inbox").glob("email_*.json")}

    assert set(submission) == inbox and len(submission) == 520
    assert set(submission) == set(json.loads((ROOT / "data" / "sample_submission.json").read_text()))


def test_every_entry_fits_contract_5_and_its_rules() -> None:
    schema = load_contract("SubmissionEntry")
    for email_id, entry in build(saved_results()).items():
        assert validate(entry, schema, email_id, []) == [], email_id
        mismatch = entry["status"] == "MISMATCH"
        assert entry["has_defect"] is mismatch, email_id                    # true iff MISMATCH
        assert bool(entry["defect_fields"]) is mismatch, email_id           # non-empty only then
        assert (entry["review_reason"] is not None) is (entry["status"] == "NEEDS_REVIEW"), email_id


def test_it_says_what_the_page_says() -> None:
    results = {e["id"]: e for e in saved_results()}
    for email_id, entry in build(list(results.values())).items():
        e = results[email_id]
        assert entry["category"] == e["category"]
        if e["category"] == "BL_COMPARISON":
            assert (entry["status"], entry["defect_fields"]) == (e["status"], e["defect_fields"])
        else:
            assert entry["status"] == "OK" and entry["defect_fields"] == []


def test_the_command_writes_the_file(tmp_path: Path) -> None:
    out = tmp_path / "submission.json"
    main(["--out", str(out)])

    assert len(json.loads(out.read_text(encoding="utf-8"))) == 520
