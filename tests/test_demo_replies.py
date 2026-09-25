"""Reply drafts on the demo account, written in advance and labelled as samples.

Live mail gets its draft from the AI (backend/reply.py). The demo account calls no model, so
until now its invoice and general emails had no draft at all. These drafts are written by
hand for the demo (by Claude, on 25 Sep), one per kind of email, filled in from each email.
They are not Ship Happens' output, so the page says so wherever one is shown.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from cli.demo_replies import sample_reply, sender_name
from cli.make_results import build_email

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
CLASSIFICATIONS = ROOT / "results" / "classifications"


def saved_results() -> list[dict]:
    src = (ROOT / "frontend" / "results.js").read_text(encoding="utf-8")
    return json.loads(src[src.index("["): src.rindex("]") + 1])


def test_every_demo_invoice_and_general_email_has_a_sample_draft() -> None:
    """All but the 15 automated notices: nobody replies to an automated sender."""
    results = saved_results()
    wanted = [e for e in results if e["category"] in ("INVOICE_QUERY", "GENERAL") and e.get("intent") != "system_notice"]

    assert len(wanted) == 120
    assert all(e.get("draft_reply") and e.get("draft_by") == "sample" for e in wanted)


def test_no_other_demo_email_has_a_sample_draft() -> None:
    """SI vs BL replies come from the page's own template; SI requests and spam get none,
    as in live mail, where only INVOICE_QUERY and GENERAL are drafted."""
    others = [e for e in saved_results()
              if e["category"] not in ("INVOICE_QUERY", "GENERAL") or e.get("intent") == "system_notice"]
    assert not [e["id"] for e in others if "draft_reply" in e or "draft_by" in e]


@pytest.mark.parametrize("email_id,must_say", [
    ("email_500", ["Dear", "5250078299", "ROXCEL TRADING GMBH", "cancel"]),
    ("email_497", ["Dear Arlene Yamomo,", "5250076025", "THC"]),
    ("email_490", ["5250076684", "GR"]),
    ("email_473", ["I283337218", "D&D"]),
    ("email_464", ["Dear Team,", "NAP 914 V.BS007"]),
    ("email_415", ["Dear Team,", "New Year"]),
    ("email_488", ["Dear Team,", "outstanding"]),
])
def test_a_draft_answers_the_email_it_belongs_to(email_id: str, must_say: list[str]) -> None:
    entry = build_email(DATA / "inbox" / f"{email_id}.json", DATA, CLASSIFICATIONS)

    for words in must_say:
        assert words.lower() in entry["draft_reply"].lower(), (email_id, words)


def test_a_draft_invents_no_amount_or_date() -> None:
    """Like the live drafter, a sample never states a charge, a total or a date the email
    did not give: it acknowledges and says what happens next."""
    for e in saved_results():
        if "draft_reply" not in e:
            continue
        numbers = set(re.findall(r"\d+(?:[.,]\d+)*", e["draft_reply"]))
        assert numbers <= set(re.findall(r"\d+(?:[.,]\d+)*", e["subject"] + " " + e["body"])), e["id"]


@pytest.mark.parametrize("body,expected", [
    ("Hi,\nQuery.\n\nBest Regards,\nTeo Ei Leen\nShipping Documentation", "Teo Ei Leen"),
    ("Dear Team,\nList attached.\n\nRegards,\nDocumentation", None),
    ("Warm regards,\nManagement", None),
    ("No sign-off at all", None),
])
def test_the_greeting_uses_the_senders_full_name_or_team(body: str, expected: str | None) -> None:
    assert sender_name(body) == expected


def test_an_intent_with_no_sample_gets_no_draft() -> None:
    assert sample_reply("system_notice", [], "This is an automated notification.") is None
    assert sample_reply(None, [], "Lunch at 1?") is None


# ---- the page ----------------------------------------------------------------------------

INDEX = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
I18N = (ROOT / "frontend" / "i18n.js").read_text(encoding="utf-8")
LABEL = "Sample reply written for the demo, not drafted by Ship Happens' AI."


def test_the_reply_box_says_a_sample_is_a_sample() -> None:
    assert f'e.draft_by==="sample"?`<div class="small mute sample">${{t("{LABEL}")}}</div>`:""' in INDEX
    assert I18N.count(f'"{LABEL}":') == 2
