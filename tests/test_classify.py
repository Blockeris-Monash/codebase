"""Qwen classifier request: the network call is faked, so these run offline."""
from __future__ import annotations

import json

import pytest

from backend import classify


@pytest.fixture(autouse=True)
def fake_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("QWEN_API_KEY", "test-key")


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
