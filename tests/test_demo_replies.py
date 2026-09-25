"""Reply drafts on the demo account: written by Claude in advance, shown when asked for.

Live mail gets its draft from the AI (backend/reply.py) when the person presses Draft a reply
(#152). The demo account calls no model, so each of its invoice and general emails carries a
draft written in advance by Claude (on 25 Sep, one per email, from that email alone), and the
page shows it the same way: behind Draft a reply, labelled as written by Claude for the demo.

These replaced one template per kind of email (#151).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from cli.demo_replies import DRAFTS, demo_draft
from cli.make_results import build_email

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
CLASSIFICATIONS = ROOT / "results" / "classifications"


def saved_results() -> list[dict]:
    src = (ROOT / "frontend" / "results.js").read_text(encoding="utf-8")
    return json.loads(src[src.index("["): src.rindex("]") + 1])


def wanted(e: dict) -> bool:
    """All invoice and general mail but the 15 automated notices: nobody replies to those."""
    return e["category"] in ("INVOICE_QUERY", "GENERAL") and e.get("intent") != "system_notice"


def test_every_demo_invoice_and_general_email_can_be_drafted_on_request() -> None:
    results = [e for e in saved_results() if wanted(e)]

    assert len(results) == 120
    for e in results:
        assert e["can_draft"] is True and e["draft_by"] == "claude" and e["demo_draft"], e["id"]
        assert "draft_reply" not in e, f"{e['id']} would show its reply before Draft a reply is pressed"


def test_no_other_demo_email_has_a_draft() -> None:
    """SI vs BL replies come from the page's own template; SI requests and spam get none,
    as in live mail, where only INVOICE_QUERY and GENERAL are drafted."""
    others = [e for e in saved_results() if not wanted(e)]
    assert not [e["id"] for e in others if {"draft_reply", "demo_draft", "draft_by", "can_draft"} & set(e)]


def test_each_draft_belongs_to_its_own_email() -> None:
    """Written from each email: its own invoice, BL, vessel or customer, and the name it was signed with."""
    for email_id, draft in DRAFTS.items():
        body = json.loads((DATA / "inbox" / f"{email_id}.json").read_text(encoding="utf-8"))["body"]
        key = re.search(r"invoice (\d{10})|charges for (\S+?)\.|Vessel (.+?) berthed|summary for (.+?)\. ", body)
        if key:
            assert [g for g in key.groups() if g][0] in draft, email_id
        signed = re.search(r"Best Regards,\s*\n\s*([^\n]+)", body)
        if signed:
            assert draft.startswith(f"Dear {signed.group(1).strip()},"), email_id
        assert draft.endswith("\n\nBest regards,\nGlobeTrans Support Team"), email_id


def test_a_draft_invents_no_amount_or_date() -> None:
    """Like the live drafter, a draft never states a charge, a total or a date the email
    did not give: it acknowledges and says what happens next."""
    for email_id, draft in DRAFTS.items():
        email = json.loads((DATA / "inbox" / f"{email_id}.json").read_text(encoding="utf-8"))
        numbers = set(re.findall(r"\d+(?:[.,]\d+)*", draft))
        assert numbers <= set(re.findall(r"\d+(?:[.,]\d+)*", email["subject"] + " " + email["body"])), email_id


def test_the_builder_attaches_the_draft_to_its_email() -> None:
    entry = build_email(DATA / "inbox" / "email_500.json", DATA, CLASSIFICATIONS)

    assert entry["demo_draft"] == demo_draft("email_500")
    assert "5250078299" in entry["demo_draft"] and "ROXCEL TRADING GMBH" in entry["demo_draft"]
    assert demo_draft("email_001") is None


# ---- the page ----------------------------------------------------------------------------

INDEX = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
I18N = (ROOT / "frontend" / "i18n.js").read_text(encoding="utf-8")
LABEL = "Written in advance by Claude for the demo. In your own mailbox, Ship Happens' AI drafts the reply."


def function(name: str) -> str:
    body = INDEX[INDEX.index(f"function {name}("):]
    return body[:body.index("\n}")]


def test_a_demo_draft_opens_on_draft_a_reply_without_calling_the_backend() -> None:
    draft = function("draftLive")

    assert "e.demo_draft" in draft
    # the demo branch comes before any sign-in check or fetch, so the demo never calls the AI
    assert draft.index("e.demo_draft") < draft.index('fetch(')
    assert draft.index("e.demo_draft") < draft.index("if(!token)")


def test_the_reply_box_says_who_wrote_a_demo_draft() -> None:
    assert f'e.draft_by==="claude"?`<div class="small mute sample">${{t("{LABEL}")}}</div>`:""' in INDEX
    assert I18N.count(f'"{LABEL}":') == 2
    assert "Sample reply written for the demo" not in INDEX + I18N
