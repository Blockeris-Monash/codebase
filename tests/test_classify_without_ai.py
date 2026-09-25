"""Sorting an email when the AI is not needed, or not answering.

On 25 Sep the live mailbox lost every email for two minutes: Qwen timed out through the
proxy and the Gemini backup had used its 20 free requests, so classification raised and
each email became "(could not be checked)". An email carrying both an SI and a draft BL
never needed the AI to be sorted - in the organizer's dataset all 124 such emails are
BL_COMPARISON - and the comparison itself reads the labels first (#122). So:

- an SI and BL pair is sorted by rule, with no model call;
- anything else that the AI cannot sort is filed by the keyword rule instead of lost.

Both say decided_by "rule", the only other value contract 02 allows, so the scorer and
the page never present a rule as the AI.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from fastapi import HTTPException

from backend import app as app_module
from backend.app import AI_DID_NOT_ANSWER, SI_AND_BL_ATTACHED, sort_email
from backend.classify import ClassificationResult, EmailInput

ROOT = Path(__file__).resolve().parents[1]


def email(subject: str = "Yo how are u", body: str = "Yo milk,\nhere is your job.", attachments=()) -> EmailInput:
    return EmailInput(email_id="gmail_1a0d76d9bd3c78f1", from_email="a@b.example", subject=subject,
                      body=body, attachments=list(attachments))


def ai_answers(category: str = "GENERAL"):
    calls = []

    async def classify(e):
        calls.append(e.email_id)
        return ClassificationResult(email_id=e.email_id, category=category, decided_by="llm",
                                    confidence=0.85, evidence="model")
    classify.calls = calls
    return classify


async def ai_down(e):
    raise HTTPException(status_code=502, detail="The read operation timed out")


def test_an_si_and_bl_pair_is_sorted_without_asking_the_ai(monkeypatch) -> None:
    classify = ai_answers()
    monkeypatch.setattr(app_module, "classify", classify)

    found = asyncio.run(sort_email(email(attachments=["x/gmail_1_SI.xlsx", "x/gmail_1_BL.docx"])))

    assert classify.calls == []
    assert (found.category, found.decided_by, found.confidence) == ("BL_COMPARISON", "rule", 1.0)
    assert found.evidence == SI_AND_BL_ATTACHED


def test_an_si_and_bl_pair_is_sorted_even_while_the_ai_is_down(monkeypatch) -> None:
    monkeypatch.setattr(app_module, "classify", ai_down)

    found = asyncio.run(sort_email(email(attachments=["x/gmail_1_SI.pdf", "x/gmail_1_BL.pdf"])))

    assert found.category == "BL_COMPARISON"


@pytest.mark.parametrize("attachments", [[], ["x/gmail_1_SI.pdf"], ["x/gmail_1_SI.pdf", "x/gmail_1_attachment.pdf"]])
def test_anything_short_of_a_pair_still_asks_the_ai(monkeypatch, attachments) -> None:
    """An SI alone, or an SI with a packing list, is the AI's call (the prompt has rules for it)."""
    classify = ai_answers("SI_REQUEST")
    monkeypatch.setattr(app_module, "classify", classify)

    found = asyncio.run(sort_email(email(attachments=attachments)))

    assert classify.calls and (found.category, found.decided_by) == ("SI_REQUEST", "llm")


@pytest.mark.parametrize("subject,body,attachments,expected", [
    ("Query on invoice 5250076025", "Is the THC included?", [], "INVOICE_QUERY"),
    ("Lunch", "Lunch at 1?", [], "GENERAL"),
    ("SI for 5RSG-76553", "Please find the Shipping instruction.", [], "SI_REQUEST"),
    ("Docs", "Please check.", ["x/gmail_1_SI.pdf"], "BL_COMPARISON"),
])
def test_when_the_ai_does_not_answer_the_keyword_rule_files_it(monkeypatch, subject, body, attachments, expected) -> None:
    monkeypatch.setattr(app_module, "classify", ai_down)

    found = asyncio.run(sort_email(email(subject, body, attachments)))

    assert (found.category, found.decided_by, found.evidence) == (expected, "rule", AI_DID_NOT_ANSWER)


def test_a_rule_decision_keeps_to_the_contract() -> None:
    schema = json.loads((ROOT / "contracts" / "02-ClassificationResult.schema.json").read_text(encoding="utf-8"))
    assert "rule" in schema["properties"]["decided_by"]["enum"]


# ---- the page ----------------------------------------------------------------------------

INDEX = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
I18N = (ROOT / "frontend" / "i18n.js").read_text(encoding="utf-8")


def test_the_page_only_credits_the_ai_when_the_ai_decided() -> None:
    assert 'const ai = e.decided_by==="llm";' in INDEX


@pytest.mark.parametrize("reason", [SI_AND_BL_ATTACHED, AI_DID_NOT_ANSWER])
def test_each_rule_reason_is_shown_and_translated(reason: str) -> None:
    assert f'T("{reason}")' in INDEX
    assert I18N.count(f'"{reason}":') == 2, f"{reason!r} needs a Malay and a Chinese line"
