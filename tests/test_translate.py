"""Translation for the UI's Translate button: the model call is faked, so these run offline."""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from backend import app as app_module
from backend import translate as tr


@pytest.fixture(autouse=True)
def fake_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("QWEN_API_KEY", "test-key")


def reply(text: str) -> dict:
    return {"content": [{"type": "text", "text": text}]}


def test_translates_each_text_and_keeps_the_keys() -> None:
    post = lambda url, headers, body: reply(json.dumps({"subject": "Halo", "body": "Sila semak"}))
    out = tr.translate_texts({"subject": "Hello", "body": "Please check"}, "Bahasa Malaysia", post=post)
    assert out == {"subject": "Halo", "body": "Sila semak"}


def test_the_prompt_names_the_target_language_and_carries_the_texts() -> None:
    seen: dict = {}

    def post(url: str, headers: dict, body: dict) -> dict:
        seen["prompt"] = body["messages"][0]["content"]
        return reply('{"body": "x"}')

    tr.translate_texts({"body": "Please check the BL"}, "Simplified Chinese", post=post)
    assert "Simplified Chinese" in seen["prompt"]
    assert "Please check the BL" in seen["prompt"]


def test_a_reply_wrapped_in_a_code_fence_still_parses() -> None:
    post = lambda url, headers, body: reply('```json\n{"body": "Terjemahan"}\n```')
    assert tr.translate_texts({"body": "Translation"}, "Malay", post=post) == {"body": "Terjemahan"}


def test_a_key_the_model_leaves_out_keeps_its_original_text() -> None:
    post = lambda url, headers, body: reply('{"subject": "Halo"}')
    out = tr.translate_texts({"subject": "Hello", "body": "Keep me"}, "Malay", post=post)
    assert out == {"subject": "Halo", "body": "Keep me"}


def test_blank_texts_are_not_sent_and_come_back_unchanged() -> None:
    def post(url: str, headers: dict, body: dict) -> dict:
        raise AssertionError("no model call is needed for blank text")

    assert tr.translate_texts({"body": "  "}, "Malay", post=post) == {"body": "  "}


def test_a_reply_that_is_not_json_raises() -> None:
    post = lambda url, headers, body: reply("Sorry, I cannot do that")
    with pytest.raises(tr.TranslationFailed):
        tr.translate_texts({"body": "Hello"}, "Malay", post=post)


def test_too_much_text_is_refused_before_calling_the_model() -> None:
    def post(url: str, headers: dict, body: dict) -> dict:
        raise AssertionError("must not be called")

    with pytest.raises(tr.TooMuchText):
        tr.translate_texts({"body": "x" * (tr.MAX_CHARS + 1)}, "Malay", post=post)


def test_missing_key_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("QWEN_API_KEY")
    with pytest.raises(RuntimeError):
        tr.translate_texts({"body": "Hello"}, "Malay", post=lambda *a: reply("{}"))


def test_endpoint_returns_the_translated_texts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app_module, "translate_texts", lambda texts, target: {"body": f"[{target}] {texts['body']}"})
    response = TestClient(app_module.app).post("/translate", json={"target": "Malay", "texts": {"body": "Hi"}})
    assert response.status_code == 200
    assert response.json() == {"texts": {"body": "[Malay] Hi"}}


def test_endpoint_maps_failures_to_http_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(texts: dict, target: str) -> dict:
        raise tr.TranslationFailed("bad reply")

    monkeypatch.setattr(app_module, "translate_texts", fail)
    client = TestClient(app_module.app)
    assert client.post("/translate", json={"target": "Malay", "texts": {"body": "Hi"}}).status_code == 502

    monkeypatch.setattr(app_module, "translate_texts", lambda texts, target: (_ for _ in ()).throw(tr.TooMuchText("long")))
    assert client.post("/translate", json={"target": "Malay", "texts": {"body": "Hi"}}).status_code == 413
