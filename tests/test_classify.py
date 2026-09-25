"""Qwen classifier request: the network call is faked, so these run offline."""
from __future__ import annotations

import asyncio
import json
import urllib.error

import pytest
from fastapi.testclient import TestClient

from backend import app as app_module
from backend import classify


@pytest.fixture(autouse=True)
def fake_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("QWEN_API_KEY", "test-key")
    # A Gemini key from a local .env would turn the backup on and reach the real Gemini.
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)


@pytest.fixture
def qwen_down(monkeypatch: pytest.MonkeyPatch) -> None:
    def unreachable(url: str, headers: dict, body: dict, timeout: float | None = None) -> dict:
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(classify, "http_post", unreachable)
    monkeypatch.setattr(classify.time, "sleep", lambda seconds: None)


@pytest.fixture
def gemini_answers(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    calls: list[str] = []

    def gemini_json(contents: str, system: str | None = None, schema: type | None = None) -> str:
        calls.append(contents)
        return json.dumps({"category": "INVOICE_QUERY", "confidence_tier": "0.85", "evidence": "D&D fees"})

    monkeypatch.setenv("GOOGLE_API_KEY", "test-gemini-key")
    monkeypatch.setattr(classify, "gemini_json", gemini_json)
    return calls


def reply(category: str = "SPAM") -> dict:
    text = json.dumps({"category": category, "confidence_tier": "1.0", "evidence": "prize"})
    return {"content": [{"type": "text", "text": text}]}


def test_leaves_room_for_qwens_thinking_before_the_answer() -> None:
    # Qwen thinks before it answers and that counts against max_tokens. 512 came back
    # empty for 163 of 520 emails, so the limit must stay well above that.
    sent = {}
    classify.qwen_classification_model("email", post=lambda url, headers, body: sent.update(body=body) or reply())

    assert sent["body"]["max_tokens"] >= 2048


def test_reads_the_category_from_the_reply() -> None:
    parsed = classify.qwen_classification_model("email", post=lambda url, headers, body: reply("SPAM"))

    assert parsed.category == "SPAM" and parsed.confidence_tier == "1.0"


def test_the_prompt_sends_an_si_plus_another_document_to_comparison() -> None:
    # Emails 502, 503, 505 attach an SI with a packing list or certificate of origin. They were
    # filed as GENERAL, so the wrong document was never flagged. The compare stage catches it.
    prompt = classify.CLASSIFICATION_PROMPT.lower()

    assert "packing list" in prompt and "certificate of origin" in prompt and "is bl_comparison" in prompt


def test_the_prompt_sends_a_draft_bl_request_with_nothing_attached_to_comparison() -> None:
    # 91 "please send the draft BL for checking" emails carry no files. They are comparison
    # emails, and the compare stage escalates them as a missing attachment.
    prompt = classify.CLASSIFICATION_PROMPT

    assert "even with nothing attached" in prompt
    assert "NOT BL_COMPARISON" not in prompt


def test_the_prompt_keeps_staff_reminders_and_greetings_out_of_si_request() -> None:
    assert "A general reminder to all staff" in classify.CLASSIFICATION_PROMPT


def test_the_prompt_keeps_a_plain_si_email_out_of_comparison() -> None:
    assert "draft BL will follow later" in classify.CLASSIFICATION_PROMPT


EMAIL = classify.EmailInput(**{"email_id": "email_001", "from": "ops@example.com",
                               "subject": "D&D charges", "body": "Please explain the D&D fees."})


def test_gemini_classifies_when_qwen_is_down(qwen_down: None, gemini_answers: list[str]) -> None:
    result = asyncio.run(classify.classify_email(EMAIL))

    assert result.category == "INVOICE_QUERY" and result.confidence == 0.85
    assert "D&D charges" in gemini_answers[0]


def test_without_a_gemini_key_qwen_being_down_is_still_a_failure(qwen_down: None) -> None:
    with pytest.raises(classify.ClassificationFailed):
        asyncio.run(classify.classify_email(EMAIL))


def test_the_batch_run_never_uses_gemini(qwen_down: None, gemini_answers: list[str], tmp_path) -> None:
    # The saved classifications feed the quoted numbers, so one model must make all of them.
    failed = asyncio.run(classify.classify_many([EMAIL], out_dir=tmp_path))

    assert [email_id for email_id, _ in failed] == ["email_001"] and gemini_answers == []


def test_classify_endpoint_answers_through_gemini_when_qwen_is_down(qwen_down: None, gemini_answers: list[str]) -> None:
    response = TestClient(app_module.app).post("/classify", json=EMAIL.model_dump(by_alias=True))

    assert response.status_code == 200 and response.json()["category"] == "INVOICE_QUERY"
