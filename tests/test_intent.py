"""A finer intent and a plain-English title for each email.

The five categories say which queue an email belongs in; the intent says what the sender
wants, and the title says it in one line instead of a subject such as
"AFRT - CALLAO_PERU - YM(YMJAI926322399) - 5RVN-11404 - 5250072886 - INTERNATIONAL FOREST P".

Both come from plain rules, not a model, so the classifier and its saved results are untouched.
tests/data/intent_labels.json is the check: every one of the 520 organizer emails, labelled by
reading each of the 55 distinct body wordings in the dataset (null for spam).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.intent import INTENTS, about, email_intent
from cli.make_results import build_email

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
CLASSIFICATIONS = ROOT / "results" / "classifications"
LABELS = json.loads((ROOT / "tests" / "data" / "intent_labels.json").read_text(encoding="utf-8"))


def saved_results() -> list[dict]:
    src = (ROOT / "frontend" / "results.js").read_text(encoding="utf-8")
    return json.loads(src[src.index("["): src.rindex("]") + 1])


def test_every_organizer_email_gets_the_intent_it_was_labelled_with() -> None:
    wrong = []
    for e in saved_results():
        got = email_intent(e["category"], e["subject"], e["body"], awaiting=bool(e.get("awaiting")))
        if got != LABELS[e["id"]]:
            wrong.append((e["id"], LABELS[e["id"]], got))

    assert not wrong, f"{len(wrong)} emails disagree with the hand labels, e.g. {wrong[:5]}"


def test_the_91_draft_bl_requests_are_one_intent() -> None:
    """The roadmap's chase list starts from these, so they must stay exactly the 91."""
    assert sum(1 for i in LABELS.values() if i == "chase_draft_bl") == 91


def test_every_intent_belongs_to_one_category() -> None:
    assert set(LABELS.values()) - {None} <= set(INTENTS)


def test_wording_no_rule_knows_has_no_intent() -> None:
    """A live email the rules have never seen keeps its subject rather than a wrong title."""
    assert email_intent("GENERAL", "Lunch on Friday?", "Anyone free for lunch on Friday?") is None


def test_spam_has_no_intent() -> None:
    assert email_intent("SPAM", "You won", "Claim your prize now, bitcoin inside") is None


def test_an_intent_is_only_given_inside_its_own_category() -> None:
    """An invoice email that mentions a berthing report is still an invoice email."""
    assert email_intent("INVOICE_QUERY", "", "Query on invoice 1: berthing report attached") is None


@pytest.mark.parametrize("email_id,expected", [
    ("email_509", ["INTERNATIONAL FOREST PRODUCTS LLC", "Callao, Peru"]),
    ("email_510", ["SAFQA LIMITED", "Mersin, Turkey"]),
    ("email_484", ["ROXCEL TRADING GMBH", "Apapa, Nigeria"]),
    ("email_493", ["KPP-ANTALIS (SINGAPORE) PTE. LTD.", "Jebel Ali, UAE"]),
    ("email_487", ["3S PAPER PRODUCTS SDN BHD", "Valparaiso, Chile"]),
    ("email_514", ["LE HAVRE V.QI540A"]),
    ("email_512", ["PO 25041"]),
    ("email_500", ["5250078299", "ROXCEL TRADING GMBH"]),
    ("email_497", ["5250076025"]),
    ("email_464", ["NAP 914 V.BS007"]),
    ("email_463", ["MARCOPOLO 810 V.BS005"]),
])
def test_the_title_names_who_and_where(email_id: str, expected: list[str]) -> None:
    record = json.loads((DATA / "inbox" / f"{email_id}.json").read_text(encoding="utf-8"))
    intent = LABELS[email_id]

    assert about(intent, record["subject"], record["body"]) == expected


def test_a_title_part_never_invents_text() -> None:
    """Every part is copied from the email (ports only change case and punctuation)."""
    for e in saved_results():
        intent = LABELS[e["id"]]
        if intent is None:
            continue
        text = (e["subject"] + " " + e["body"]).upper().replace("_", " ")
        for part in about(intent, e["subject"], e["body"]):
            words = part.upper().replace(",", " ").split()
            assert all(w in text for w in words), (e["id"], part)


def test_an_email_entry_carries_its_intent_and_title_parts() -> None:
    entry = build_email(DATA / "inbox" / "email_484.json", DATA, CLASSIFICATIONS)

    assert entry["intent"] == "submit_si"
    assert entry["about"] == ["ROXCEL TRADING GMBH", "Apapa, Nigeria"]


def test_an_email_with_no_intent_has_no_keys_rather_than_nulls() -> None:
    """The screen tests for the key, as it does for `ref`."""
    spam = next(e for e in saved_results() if e["category"] == "SPAM")
    entry = build_email(DATA / "inbox" / f"{spam['id']}.json", DATA, CLASSIFICATIONS)

    assert "intent" not in entry and "about" not in entry


def test_the_saved_results_carry_the_intents() -> None:
    results = saved_results()

    assert sum(1 for e in results if "intent" in e) == 480
    assert all(e.get("intent") == LABELS[e["id"]] for e in results)


# ---- the page ----------------------------------------------------------------------------

INDEX = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
I18N = (ROOT / "frontend" / "i18n.js").read_text(encoding="utf-8")


def test_the_list_row_shows_the_title() -> None:
    assert '<span class="sub">${hl(title(e))}</span>' in INDEX


def test_the_email_heading_is_the_title_with_the_subject_under_it() -> None:
    assert "<h2>${esc(title(e))}</h2>" in INDEX
    assert '${e.intent?`<div class="mute small subj">${esc(e.subject)}</div>`:""}' in INDEX


def test_search_still_finds_the_subject_and_the_title() -> None:
    assert '(e.subject+" "+title(e)+" "+e.from' in INDEX


@pytest.mark.parametrize("intent", sorted(set(LABELS.values()) - {None}))
def test_every_intent_label_is_translated(intent: str) -> None:
    label = INTENTS[intent][1]
    assert f'{intent}:T("{label}")' in INDEX
    assert I18N.count(f'"{label}":') == 2, f"{label!r} needs a Malay and a Chinese line"
