"""A real mailbox holds more than shipping mail. GitHub notifications and a broker's
statement were filed as SPAM, because the prompt knew only shipping work: GENERAL
was "internal operational updates" and SPAM included "external spam".

Two checks now. The prompt says what spam is in general terms (deceptive, or junk
nobody asked for), never by sender. And live mail carries one more line: it is in the
Gmail inbox, so Gmail's own spam filter already let it through. The senders below are
samples for the live check only; they appear nowhere in the prompt.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from backend import classify
from tests.live_gate import needs_live

ROOT = Path(__file__).resolve().parents[1]
PROMPT = classify.CLASSIFICATION_PROMPT


def test_the_prompt_files_genuine_notifications_as_general() -> None:
    assert "notifications, statements and alerts from services the person uses" in PROMPT
    assert "When unsure between GENERAL and SPAM, choose GENERAL" in PROMPT


def test_the_prompt_no_longer_calls_any_outside_mail_spam() -> None:
    assert "external spam" not in PROMPT


def test_the_prompt_names_no_sender() -> None:
    for name in ("github", "interactive brokers", "ibkr", "google"):
        assert name not in PROMPT.lower(), name


def prompt_for(email_id: str) -> str:
    seen: list[str] = []

    def model(prompt: str) -> classify.ClassificationSchema:
        seen.append(prompt)
        return classify.ClassificationSchema(category="GENERAL", confidence_tier="1.0", evidence="x")

    email = classify.EmailInput(email_id=email_id, **{"from": "a@b.example"}, subject="s", body="b")
    asyncio.run(classify.classify_email(email, model=model))
    return seen[0]


def test_live_mail_tells_the_model_gmail_already_passed_it() -> None:
    assert classify.GMAIL_LINE in prompt_for("gmail_18c2f4e9a1b3d5f7")
    assert "Gmail's own spam filter has already let it through" in PROMPT


def test_dataset_mail_never_claims_to_be_from_gmail() -> None:
    """The saved dataset results must not shift: those emails were never in anyone's Gmail."""
    assert "Gmail" not in prompt_for("email_015")


def test_the_prompt_still_names_what_spam_is() -> None:
    for sign in ("phishing", "verify", "bank details", "prize", "crypto"):
        assert sign in PROMPT.lower(), sign


REAL_MAIL = [
    ("notifications@github.com", "[Blockeris-Monash/codebase] Pull request #83 merged",
     "Merged #83 into main. You are receiving this because you authored the thread. Reply to this email directly or view it on GitHub."),
    ("donotreply@interactivebrokers.com", "Daily Activity Statement for U1234567",
     "Your daily activity statement for 24 September 2026 is now available in Client Portal. Please log in to view it."),
    ("no-reply@accounts.google.com", "Security alert",
     "A new sign-in to your Google Account was detected on a Windows device. If this was you, you don't need to do anything."),
    ("friend@gmail.com", "Dinner on Saturday?", "Hey, are you free for dinner after the finals on Saturday?"),
]


@needs_live("QWEN_API_KEY")
@pytest.mark.parametrize("sender,subject,body", REAL_MAIL, ids=["github", "broker", "google", "friend"])
def test_genuine_mail_is_not_spam(sender: str, subject: str, body: str) -> None:
    email = classify.EmailInput(email_id="gmail_18c2f4e9a1b3d5f7", **{"from": sender}, subject=subject, body=body)

    result = asyncio.run(classify.classify_email(email, model=classify.qwen_classification_model))

    assert result.category == "GENERAL", result.evidence


SPAM_IDS = sorted(p.stem for p in (ROOT / "results" / "classifications").glob("email_*.json")
                  if json.loads(p.read_text(encoding="utf-8"))["category"] == "SPAM")


@needs_live("QWEN_API_KEY")
@pytest.mark.parametrize("email_id", SPAM_IDS)
def test_the_datasets_spam_is_still_spam(email_id: str) -> None:
    record = ROOT / "data" / "inbox" / f"{email_id}.json"
    if not record.exists():
        pytest.skip("dataset not present")
    email = classify.EmailInput(**json.loads(record.read_text(encoding="utf-8")))

    result = asyncio.run(classify.classify_email(email, model=classify.qwen_classification_model))

    assert result.category == "SPAM", result.evidence
