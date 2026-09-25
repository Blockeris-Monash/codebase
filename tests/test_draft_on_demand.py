"""A live email's reply is drafted when the person asks for it, not when the mailbox is checked (#149).

Every General and Invoice email in a live mailbox got a paid Gemini draft the moment it was
checked, and a Render restart checked (and drafted) the whole inbox again. Most of that mail
(GitHub, Grab, bank notices) is never answered. Now checking only sorts the email, and
POST /draft-reply writes the draft when the person presses Draft a reply, once per email.

Offline: the draft is a fake, so no test here spends a model call.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from backend import app as app_module
from backend import middleware, reply
from tests.test_gmail_mailbox import google, poll  # noqa: F401  (google is a fixture)

A = {"Authorization": "Bearer token-a"}
LUNCH = "gmail_18c2f4e9a1b3d5f8"      # GENERAL in the fake mailbox
SI_AND_BL = "gmail_18c2f4e9a1b3d5f7"  # BL_COMPARISON: its reply comes from a template


@pytest.fixture
def drafts(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Every draft the model would have been paid for."""
    asked: list[str] = []

    def draft(email, category):
        asked.append(email.email_id)
        return reply.Draft(f"Hi, about {email.subject}: thanks for your email.", grounded=False)

    monkeypatch.setattr(reply, "generate_rag_reply", draft)
    return asked


def test_checking_the_mailbox_drafts_nothing(google, drafts) -> None:
    emails = {e["id"]: e for e in poll(google.client, "token-a", 2)}

    assert drafts == []
    assert "draft_reply" not in emails[LUNCH] or emails[LUNCH]["draft_reply"] is None
    assert emails[LUNCH]["can_draft"] is True
    assert not emails[SI_AND_BL].get("can_draft")


def test_asking_drafts_once_and_the_mailbox_keeps_it(google, drafts) -> None:
    poll(google.client, "token-a", 2)

    first = google.client.post("/draft-reply", json={"email_id": LUNCH}, headers=A)
    again = google.client.post("/draft-reply", json={"email_id": LUNCH}, headers=A)

    assert first.status_code == 200, first.text
    assert first.json()["draft_reply"] == "Hi, about Lunch: thanks for your email."
    assert first.json()["grounded"] is False
    assert again.json() == first.json()
    assert drafts == [LUNCH]  # the second ask was free
    kept = {e["id"]: e for e in poll(google.client, "token-a", 2)}[LUNCH]
    assert kept["draft_reply"] == first.json()["draft_reply"]


def test_a_failed_draft_says_so_and_is_not_kept(google, monkeypatch) -> None:
    poll(google.client, "token-a", 2)
    monkeypatch.setattr(reply, "generate_rag_reply", lambda email, category: None)

    failed = google.client.post("/draft-reply", json={"email_id": LUNCH}, headers=A)

    assert failed.status_code == 502
    assert "draft_reply" not in app_module.MAILBOXES["a@ours.example"]["18c2f4e9a1b3d5f8"] or \
        app_module.MAILBOXES["a@ours.example"]["18c2f4e9a1b3d5f8"]["draft_reply"] is None


def test_a_draft_needs_a_google_token(google, drafts) -> None:
    assert google.client.post("/draft-reply", json={"email_id": LUNCH}).status_code == 401
    assert drafts == []


def test_nobody_can_draft_for_someone_elses_email(google, drafts) -> None:
    poll(google.client, "token-a", 2)

    got = google.client.post("/draft-reply", json={"email_id": LUNCH}, headers={"Authorization": "Bearer token-b"})

    assert got.status_code == 404 and drafts == []


def test_an_email_not_checked_yet_or_with_a_template_reply_gets_no_model_draft(google, drafts) -> None:
    unchecked = google.client.post("/draft-reply", json={"email_id": "gmail_99"}, headers=A)
    poll(google.client, "token-a", 2)
    template = google.client.post("/draft-reply", json={"email_id": SI_AND_BL}, headers=A)

    assert unchecked.status_code == 404
    assert template.status_code == 422
    assert drafts == []


def test_drafting_counts_against_the_model_rate_limit() -> None:
    assert "/draft-reply" in middleware.LIMITED_PATHS


def test_process_email_still_drafts_for_a_caller_who_asks_for_one_email(drafts) -> None:
    """The API route answers one email at a time on request, so it keeps drafting."""
    from fastapi.testclient import TestClient

    async def classify(email):
        from backend.classify import ClassificationResult
        return ClassificationResult(email_id=email.email_id, category="GENERAL", decided_by="llm",
                                    confidence=1.0, evidence="test")

    mp = pytest.MonkeyPatch()
    mp.setattr(app_module, "classify", classify)
    try:
        got = TestClient(app_module.app).post("/process-email", json={
            "email_id": "e1", "from": "a@b.example", "subject": "Hello", "body": "Hi", "attachments": []})
    finally:
        mp.undo()

    assert got.json()["draft_reply"] == "Hi, about Hello: thanks for your email."
    assert got.json()["draft_grounded"] is False


# ---------------------------------------------------------------- the page

INDEX = (Path(__file__).resolve().parents[1] / "frontend" / "index.html").read_text(encoding="utf-8")


def function(name: str) -> str:
    body = INDEX[INDEX.index(f"function {name}("):]
    return body[:body.index("\n}")]


def test_the_page_offers_a_draft_button_for_an_email_that_can_have_one() -> None:
    actions = function("actionsHTML")

    assert "e.can_draft" in actions
    assert 'data-a="aidraft"' in actions
    assert re.search(r'a==="aidraft"\)\{[^\n]*draftLive\(id\)', INDEX)


def test_the_page_asks_for_the_draft_with_the_google_token_and_shows_it_is_working() -> None:
    live = function("draftLive")

    assert 'API_BASE + "/draft-reply"' in live
    assert '"Authorization":"Bearer " + token' in live
    assert "S.drafting" in live and "S.draftErr" in live
    assert "S.draft = draftFor(" in live  # the draft opens in the reply box, ready to edit
    assert 't("Drafting...")' in function("actionsHTML")
