"""Finding the shipment an email is about.

Their service list includes supporting the Commercial team on customer queries,
which is lookup by reference rather than triage. Two shapes appear in this
corpus: an order reference (5ALT-01226) and a carrier booking reference
(OOLU9284044566). The carrier half must demand a run of digits, because
"[A-Z]{4}[A-Z0-9]{6,}" alone also matches INTERNATIONAL and OUTSTANDING.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.mail_view import shipment_ref
from cli.make_results import build_email

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
CLASSIFICATIONS = ROOT / "results" / "classifications"


@pytest.mark.parametrize("subject,expected", [
    ("RE_ AIE - PYEONGTAEK_SOUTH KOREA - MSC(MEDUUD032119) - 5RSG-63852", "MEDUUD032119"),
    ("TO CONFIRM DOCS _ 5ALT-01226 _ JEBEL ALI_UAE", "5ALT-01226"),
    ("RE_ Draft BL NAP 914 V.BS007 NANTONG - amend BL 044", None),
])
def test_the_reference_is_read_from_the_subject(subject: str, expected: str | None) -> None:
    assert shipment_ref(subject, "") == expected


@pytest.mark.parametrize("word", [
    "INTERNATIONAL", "OUTSTANDING", "INVESTMENT", "OPPORTUNITY", "GUARANTEED", "CONNECTION",
])
def test_an_english_word_is_not_a_shipment_reference(word: str) -> None:
    """Thirteen words in these subjects match a four-letter prefix followed by
    letters. Each one would be a false reference on a reviewer's screen."""
    assert shipment_ref(f"RE_ {word} PAPER TRADING", "") is None


def test_the_subject_wins_over_the_body() -> None:
    """The reference on the row should be the one already visible in the list."""
    assert shipment_ref("order 5ALT-01226 confirmed", "booking OOLU9284044566") == "5ALT-01226"


def test_the_body_is_used_when_the_subject_has_none() -> None:
    assert shipment_ref("please confirm", "our booking is OOLU9284044566") == "OOLU9284044566"


def test_the_first_reference_wins_so_the_result_is_repeatable() -> None:
    assert shipment_ref("5ALT-01226 and 5RSG-63852", "") == "5ALT-01226"


def test_lowercase_is_found_too() -> None:
    """Subjects are upper-cased before matching, so case cannot hide a reference."""
    assert shipment_ref("order 5alt-01226 confirmed", "") == "5ALT-01226"


@pytest.mark.parametrize("subject,body", [("", ""), (None, None)])
def test_nothing_to_read_is_not_an_error(subject, body) -> None:
    assert shipment_ref(subject, body) is None


def test_an_email_entry_carries_the_reference_it_names() -> None:
    entry = build_email(DATA / "inbox" / "email_004.json", DATA, CLASSIFICATIONS)
    record = json.loads((DATA / "inbox" / "email_004.json").read_text(encoding="utf-8"))

    assert entry["ref"] in (record["subject"] + record["body"]).upper()


def test_an_email_with_no_reference_has_no_key_rather_than_a_null() -> None:
    """The screen tests for the key, so an absent reference must be absent."""
    entries = [build_email(p, DATA, CLASSIFICATIONS)
               for p in sorted((DATA / "inbox").glob("email_0[0-5]*.json"))[:40]]
    without = [e for e in entries if "ref" not in e]

    assert without, "expected at least one email with no shipment reference"
    assert all(e.get("ref") is not None for e in entries if "ref" in e)


def test_most_of_the_emails_waiting_on_a_draft_bl_can_be_chased() -> None:
    """The chase list on the roadmap is keyed on this reference, so a regex
    regression that drops the carrier half must fail here rather than quietly
    shrink the list."""
    src = (ROOT / "frontend" / "results.js").read_text(encoding="utf-8")
    results = json.loads(src[src.index("["): src.rindex("]") + 1])
    awaiting = [e for e in results if e.get("awaiting")]

    assert len(awaiting) == 91
    with_ref = [e for e in awaiting
                if shipment_ref(e["subject"], e.get("body", "")) is not None]
    assert len(with_ref) >= 62
