"""Qwen classifier batch: the network call is faked, so these run offline."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.classify import ClassificationFailed
from cli import classify_qwen as cq


@pytest.fixture(autouse=True)
def fake_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("QWEN_API_KEY", "test-key")


def reply(category: str = "BL_COMPARISON", tier: str = "0.85", evidence: str = "compare the SI and BL") -> dict:
    text = json.dumps({"category": category, "confidence_tier": tier, "evidence": evidence})
    return {"content": [{"type": "text", "text": "```json\n" + text + "\n```"}]}


EMAIL = {"email_id": "email_001", "from": "a@b.com", "subject": "RE_ check BL", "body": "please compare", "attachments": []}


def test_classifies_one_email_as_a_classification_result() -> None:
    result = cq.classify_email_qwen(EMAIL, post=lambda url, headers, body: reply())

    assert result == {"email_id": "email_001", "category": "BL_COMPARISON", "decided_by": "llm",
                      "confidence": 0.85, "evidence": "compare the SI and BL"}


def test_the_prompt_carries_the_email_and_the_five_categories() -> None:
    sent = {}
    cq.classify_email_qwen(EMAIL, post=lambda url, headers, body: sent.update(body=body) or reply())

    prompt = sent["body"]["messages"][0]["content"]
    assert "RE_ check BL" in prompt and "please compare" in prompt
    for category in ("BL_COMPARISON", "SI_REQUEST", "INVOICE_QUERY", "GENERAL", "SPAM"):
        assert category in prompt


def test_an_unknown_category_is_a_failure() -> None:
    with pytest.raises(ClassificationFailed):
        cq.classify_email_qwen(EMAIL, post=lambda url, headers, body: reply(category="MAYBE"))


def test_batch_saves_one_file_per_email_and_a_rerun_skips_them(tmp_path: Path) -> None:
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    for n in (1, 2):
        (inbox / f"email_00{n}.json").write_text(json.dumps({**EMAIL, "email_id": f"email_00{n}"}))
    out = tmp_path / "out"
    calls = []

    def post(url, headers, body):
        calls.append(1)
        return reply()

    first = cq.run_batch(inbox, out, post=post, log=lambda *_: None)
    second = cq.run_batch(inbox, out, post=post, log=lambda *_: None)

    assert first["done"] == 2 and second["done"] == 0 and second["skipped"] == 2 and len(calls) == 2
    assert json.loads((out / "email_001.json").read_text())["category"] == "BL_COMPARISON"


def test_a_failed_email_is_reported_and_not_saved(tmp_path: Path) -> None:
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / "email_001.json").write_text(json.dumps(EMAIL))
    out = tmp_path / "out"

    summary = cq.run_batch(inbox, out, post=lambda u, h, b: reply(category="NOPE"), log=lambda *_: None, retries=1)

    assert summary["failed"] == ["email_001"] and not (out / "email_001.json").exists()
