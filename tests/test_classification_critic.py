"""The classification critic: a second opinion from a different model, asked only when
there is a reason to doubt how an email was sorted, and reported every time.

The models are fakes, so these run offline and fast."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend import classify, critic, reports
from backend.classify import ClassificationSchema, EmailInput, classify_email
from backend.extract.fallback import with_fallback

ROOT = Path(__file__).resolve().parents[1]
EDGE = ROOT / "tests" / "edge_cases" / "inbox"


@pytest.fixture(autouse=True)
def no_real_models(monkeypatch: pytest.MonkeyPatch) -> None:
    """A key from a local .env would reach a real model."""
    for name in ("GOOGLE_API_KEY", "GEMINI_API_KEY", "GEMINI_CRITIC_API_KEY", "GEMINI_CRITIC_MODEL"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def filed(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    rows: list[dict] = []
    monkeypatch.setattr(reports, "file", lambda row, **how: rows.append(row))
    return rows


def says(category: str, tier: str = "1.0") -> ClassificationSchema:
    return ClassificationSchema(category=category, confidence_tier=tier, evidence="from the email")


def qwen(answer: ClassificationSchema):
    """Qwen alone, as with no backup key: every call it makes is still recorded."""
    return with_fallback(lambda prompt: answer, lambda prompt: pytest.fail("backup used"),
                         enabled=lambda: False)


def second(answer: ClassificationSchema, calls: list[str] | None = None):
    def ask(prompt: str) -> ClassificationSchema:
        if calls is not None:
            calls.append(prompt)
        return answer
    return ask


def email(subject: str = "Schedule", body: str = "Vessel berthing moved to Friday.",
          attachments: list[str] | None = None, email_id: str = "gmail_1") -> EmailInput:
    return EmailInput(**{"email_id": email_id, "from": "ops@carrier.test", "subject": subject,
                         "body": body, "attachments": attachments or []})


def edge(email_id: str) -> EmailInput:
    return EmailInput(**json.loads((EDGE / f"{email_id}.json").read_text(encoding="utf-8")))


def sort(message: EmailInput, first: ClassificationSchema, ask=None):
    return asyncio.run(classify_email(message, model=qwen(first), second_opinion=ask))


# --- when it asks ---------------------------------------------------------------

def test_a_confident_answer_with_no_warning_signs_is_not_second_guessed(filed) -> None:
    calls: list[str] = []

    result = sort(email(), says("GENERAL"), second(says("SPAM"), calls))

    assert result.category == "GENERAL" and calls == [] and filed == []


def test_the_critic_is_off_unless_asked_for(filed) -> None:
    """The saved results were made by Qwen alone; the batch run must stay that way."""
    result = sort(email(), says("GENERAL", "0.65"))

    assert result.category == "GENERAL" and result.confidence == 0.65 and filed == []


def test_the_batch_run_never_asks_for_a_second_opinion(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(classify, "qwen_classification_model", lambda prompt: says("GENERAL", "0.65"))
    monkeypatch.setattr(critic, "review", lambda *args: pytest.fail("critic ran in the batch"))

    assert asyncio.run(classify.classify_many([email(email_id="email_001")], out_dir=tmp_path)) == []


# --- what it decides ------------------------------------------------------------

def test_an_unsure_answer_that_the_second_model_agrees_with_is_kept_and_surer(filed) -> None:
    result = sort(email(), says("GENERAL", "0.65"), second(says("GENERAL", "1.0")))

    assert result.category == "GENERAL" and result.confidence == 1.0
    assert filed[0]["title"] == "Classification: second opinion agreed on GENERAL"
    assert filed[0]["context"]["tries"] == 2


def test_an_unsure_answer_changes_when_the_second_model_is_surer(filed) -> None:
    result = sort(email(), says("GENERAL", "0.65"), second(says("SI_REQUEST", "1.0")))

    assert result.category == "SI_REQUEST"
    assert filed[0]["title"] == "Classification: changed from GENERAL to SI_REQUEST"


def test_two_unsure_models_that_disagree_keep_the_first_at_050(filed) -> None:
    result = sort(email(), says("GENERAL", "0.65"), second(says("SI_REQUEST", "0.65")))

    assert result.category == "GENERAL" and result.confidence == 0.5
    assert filed[0]["title"] == "Classification: models disagreed, kept GENERAL"


def test_phishing_filed_as_a_bl_check_is_caught(filed) -> None:
    """Edge case a12: a login link dressed as a draft BL was shown to staff as a real task."""
    result = sort(edge("email_913"), says("BL_COMPARISON"), second(says("SPAM")))

    assert result.category == "SPAM"
    assert filed[0]["title"] == "Classification: changed from BL_COMPARISON to SPAM"
    assert "asks for a password or login" in filed[0]["detail"]


def test_an_automatic_reply_filed_as_a_bl_check_is_caught(filed) -> None:
    """Edge case a11: an out-of-office quoting a BL email became a task for staff."""
    result = sort(edge("email_912"), says("BL_COMPARISON"), second(says("GENERAL")))

    assert result.category == "GENERAL"


def test_an_si_and_bl_not_filed_as_a_bl_check_is_caught(filed) -> None:
    """The worst miss there is: a check that is never run, and nobody told."""
    attached = email(attachments=["gmail_1_SI.pdf", "gmail_1_BL.pdf"])

    result = sort(attached, says("GENERAL"), second(says("BL_COMPARISON")))

    assert result.category == "BL_COMPARISON"


def test_a_doubt_the_second_model_does_not_bear_out_keeps_the_first_at_050(filed) -> None:
    result = sort(edge("email_913"), says("BL_COMPARISON"), second(says("INVOICE_QUERY")))

    assert result.category == "BL_COMPARISON" and result.confidence == 0.5


# --- what it will not do ----------------------------------------------------------

def test_gemini_is_never_asked_to_check_gemini(filed) -> None:
    """Qwen was down, so the backup already gave the first answer. Asking it again
    costs quota and adds nothing, but the admin still hears why."""
    calls: list[str] = []
    down = with_fallback(lambda prompt: (_ for _ in ()).throw(RuntimeError("gateway unreachable")),
                         lambda prompt: says("GENERAL", "0.65"))

    result = asyncio.run(classify_email(email(), model=down, second_opinion=second(says("SPAM"), calls)))

    assert result.category == "GENERAL" and calls == []
    assert filed[0]["title"] == "Classification: not double-checked"


def test_a_second_opinion_that_fails_keeps_the_first_answer(filed) -> None:
    def unreachable(prompt: str) -> ClassificationSchema:
        raise RuntimeError("quota exhausted")

    result = sort(email(), says("GENERAL", "0.65"), unreachable)

    assert result.category == "GENERAL" and result.confidence == 0.65
    assert filed[0]["title"] == "Classification: second opinion failed, kept GENERAL"
    assert filed[0]["context"]["attempts"][1]["result"] == "quota exhausted"


def test_with_no_gemini_key_the_second_opinion_says_why_it_cannot_answer() -> None:
    with pytest.raises(RuntimeError, match="no Gemini key"):
        classify.gemini_second_opinion("prompt")


# --- the live service, and its own quota -----------------------------------------

def test_the_live_endpoint_asks_on_the_critics_own_key_and_model(monkeypatch, filed) -> None:
    """Limits are per Google project and per model: a separate key or model keeps a
    run of second opinions from using up what the backup needs when Qwen is down."""
    asked: list[dict] = []

    def qwen_reply(url: str, headers: dict, body: dict) -> dict:
        text = json.dumps({"category": "GENERAL", "confidence_tier": "0.65", "evidence": "berthing"})
        return {"content": [{"type": "text", "text": text}]}

    def gemini_json(contents, system=None, schema=None, key=None, model=None) -> str:
        asked.append({"key": key, "model": model})
        return json.dumps({"category": "GENERAL", "confidence_tier": "1.0", "evidence": "berthing"})

    monkeypatch.setenv("QWEN_API_KEY", "test-key")
    monkeypatch.setenv("GEMINI_CRITIC_API_KEY", "critic-key")
    monkeypatch.setenv("GEMINI_CRITIC_MODEL", "critic-model")
    monkeypatch.setattr(classify, "http_post", qwen_reply)
    monkeypatch.setattr(classify, "gemini_json", gemini_json)

    response = TestClient(__import__("backend.app", fromlist=["app"]).app).post(
        "/classify", json=email().model_dump(by_alias=True))

    assert response.status_code == 200 and response.json()["confidence"] == 1.0
    assert asked == [{"key": "critic-key", "model": "critic-model"}]


# --- how often, on real mail --------------------------------------------------------

def test_the_dataset_needs_a_second_opinion_for_one_email_in_a_hundred() -> None:
    """Measured on the 520 saved answers: only the 5 where Qwen was 0.65 sure. None of
    the wording rules fires on real mail, so the critic costs almost no quota."""
    tiers = {1.0: "1.0", 0.85: "0.85", 0.65: "0.65", 0.5: "0.50"}
    doubted = []
    for path in sorted((ROOT / "data" / "inbox").glob("*.json")):
        message = EmailInput(**json.loads(path.read_text(encoding="utf-8")))
        saved = json.loads((ROOT / "results" / "classifications" / path.name).read_text(encoding="utf-8"))
        first = says(saved["category"], tiers[round(saved["confidence"], 2)])
        if critic.doubts(message, first):
            doubted.append(message.email_id)

    assert doubted == ["email_012", "email_083", "email_252", "email_347", "email_464"]


def test_the_amendment_request_edge_case_is_a_known_miss() -> None:
    """Edge case a9 gives no signal to go on, so it is not doubted. Said, not hidden."""
    assert critic.doubts(edge("email_910"), says("BL_COMPARISON")) == []
