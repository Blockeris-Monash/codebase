"""Two independently written comparators, one verdict.

`backend/comparator.py` (JJ) and the reference path in `tools` were written
separately from the same brief. Running both over every comparison email and
requiring identical verdicts is stronger evidence than either one's own tests:
a shared mistake would have to be made twice, the same way.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from comparator import compare  # noqa: E402

from make_fixtures import build  # noqa: E402

COMPARISON_EMAILS = 126


def comparison_emails(data_dir: Path) -> list[dict[str, object]]:
    return [json.loads(p.read_text())
            for p in sorted((data_dir / "inbox").glob("email_*.json"))
            if json.loads(p.read_text())["attachments"]]


def both_verdicts(data_dir: Path, email: dict[str, object]) -> tuple[tuple, tuple]:
    _, extracts, ours = build(str(data_dir), email)
    by_role = {e["declared_role"]: e for e in extracts}
    theirs = compare(str(email["email_id"]), by_role.get("SI"), by_role.get("BL"))

    return ((theirs.status, theirs.review_reason, sorted(theirs.defect_fields)),
            (ours["status"], ours["review_reason"], sorted(ours["defect_fields"])))


def test_the_corpus_has_the_expected_number_of_comparisons(data_dir: Path) -> None:
    assert len(comparison_emails(data_dir)) == COMPARISON_EMAILS


def test_both_comparators_agree_on_every_email(data_dir: Path) -> None:
    """Status, escalation reason and the exact defect set, all 126."""
    disagreements = []
    for email in comparison_emails(data_dir):
        theirs, ours = both_verdicts(data_dir, email)
        if theirs != ours:
            disagreements.append(f"{email['email_id']}: {theirs} != {ours}")

    assert disagreements == []


@pytest.mark.parametrize("email_id,reason", [
    ("email_511", "unreadable"),        # corrupt PDF, no title to read
    ("email_512", "unreadable"),        # scanned image, no text layer
    ("email_501", "wrong_doc_type"),    # BL slot holds a commercial invoice
    ("email_506", "missing_attachment"),
    ("email_516", "missing_value"),
])
def test_escalation_reason_survives_both_paths(data_dir: Path, email_id: str,
                                               reason: str) -> None:
    """A document that will not open has no title, so its type is unknown
    rather than wrong - unreadable has to be checked before doc type."""
    email = json.loads((data_dir / "inbox" / f"{email_id}.json").read_text())
    theirs, ours = both_verdicts(data_dir, email)

    assert theirs[1] == reason
    assert ours[1] == reason
