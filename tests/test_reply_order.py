"""Reply drafts: Gemini first, Qwen as the backup.

Timed on 25 Sep, Qwen took 19.0, 35.2 and 37.9 s to draft a reply (600 to 700 tokens,
about twice a classification), so with a 15 s limit it never finished: every live draft
waited 15 s for Qwen to fail and was then written by Gemini (#137, #148). Gemini answers
in about 4 s. So for replies only, Gemini goes first and Qwen is the backup, with the time
a reply really needs. Without a Gemini key, Qwen drafts alone, as before.
"""
from __future__ import annotations

import time

import pytest

from backend import reply
from backend.classify import EmailInput
from backend.extract.circuit_breaker import CircuitBreaker

EMAIL = EmailInput(email_id="gmail_1", from_email="a@b.example", subject="Query on invoice 5250076025",
                   body="Is the THC included or billed separately?", attachments=[])


@pytest.fixture
def models(monkeypatch):
    calls: list[str] = []
    state = {"gemini": "Hi, from Gemini.", "qwen": "Hi, from Qwen.", "gemini_delay": 0.0}

    def gemini(prompt, system_instruction):
        calls.append("gemini")
        time.sleep(state["gemini_delay"])
        if isinstance(state["gemini"], Exception):
            raise state["gemini"]
        return state["gemini"]

    def qwen(prompt, system_instruction):
        calls.append("qwen")
        return state["qwen"]

    monkeypatch.setattr(reply, "retrieve_policies", lambda query, top_k=3: [])
    monkeypatch.setattr(reply, "gemini_generate", gemini)
    monkeypatch.setattr(reply, "qwen_generate", qwen)
    monkeypatch.setattr(reply, "GEMINI_API_KEY", "set")
    monkeypatch.setattr(reply, "qwen_reply_breaker", CircuitBreaker())
    state["calls"] = calls
    return state


def test_gemini_drafts_first_and_qwen_is_not_asked(models) -> None:
    assert reply.generate_rag_reply(EMAIL, "INVOICE_QUERY") == "Hi, from Gemini."
    assert models["calls"] == ["gemini"]


def test_qwen_drafts_when_gemini_fails(models) -> None:
    models["gemini"] = RuntimeError("429 RESOURCE_EXHAUSTED")

    assert reply.generate_rag_reply(EMAIL, "INVOICE_QUERY") == "Hi, from Qwen."
    assert models["calls"] == ["gemini", "qwen"]


def test_qwen_drafts_when_gemini_stalls(models, monkeypatch) -> None:
    monkeypatch.setattr(reply, "GEMINI_REPLY_SECONDS", 0.2)
    models["gemini_delay"] = 1.0

    assert reply.generate_rag_reply(EMAIL, "INVOICE_QUERY") == "Hi, from Qwen."


def test_without_a_gemini_key_qwen_drafts_alone(models, monkeypatch) -> None:
    monkeypatch.setattr(reply, "GEMINI_API_KEY", None)

    assert reply.generate_rag_reply(EMAIL, "GENERAL") == "Hi, from Qwen."
    assert models["calls"] == ["qwen"]


def test_gemini_gets_longer_than_its_slowest_logged_reply() -> None:
    """#137 logged Gemini replies of 3.5 to 14.4 s; 15 s would cut the slow ones off."""
    assert reply.GEMINI_REPLY_SECONDS >= 20


def test_qwen_gets_the_time_a_reply_needs(monkeypatch) -> None:
    """Measured at 19 to 38 s. The 15 s the other stages use would fail every draft."""
    seen = {}

    class Answer:
        def __enter__(self): return self
        def __exit__(self, *exc): return False
        def read(self): return b'{"content": [{"type": "text", "text": "ok"}]}'

    def urlopen(request, timeout):
        seen["timeout"] = timeout
        return Answer()

    monkeypatch.setenv("QWEN_API_KEY", "k")
    monkeypatch.setenv("QWEN_TIMEOUT_SECONDS", "15")  # the other stages' limit must not apply here
    monkeypatch.setattr(reply.urllib.request, "urlopen", urlopen)

    assert reply.qwen_generate("prompt", "system") == "ok"
    assert seen["timeout"] == reply.QWEN_REPLY_SECONDS >= 45
