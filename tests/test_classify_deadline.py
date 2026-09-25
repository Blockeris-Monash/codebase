"""One classification never runs past its budget (issues #109 item 2 and #111).

JJ's change (c585e49) replaced the fixed 4 tries with a 25 s budget across every try,
and kept the upstream status code. Two gaps were left and are closed here:

- the budget was only checked between tries, so a call that hung rather than failed
  ran its full 15 s past it. Each try now gets at most the time that is left.
- with a Gemini key, Gemini only took over after 60 s. Classification now switches
  after 15 s, as extraction already does (app.py).
"""
from __future__ import annotations

import asyncio
import io
import time
import urllib.error
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend import app as app_module
from backend import classify
from backend.classify import EmailInput

CLASSIFY_SOURCE = (Path(__file__).resolve().parents[1] / "backend" / "classify.py").read_text(encoding="utf-8")


@pytest.fixture(autouse=True)
def fake_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("QWEN_API_KEY", "test-key")
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)


def http_error(code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError("https://gateway.example/v1/messages", code, "upstream", {}, io.BytesIO(b""))


def test_a_hanging_gateway_never_runs_past_the_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    given: list[float] = []

    def hangs(url: str, headers: dict, body: dict, timeout: float | None = None) -> dict:
        given.append(timeout)
        time.sleep(timeout)  # what urlopen does when the gateway never answers
        raise TimeoutError("timed out")

    monkeypatch.setattr(classify, "http_post", hangs)
    started = time.monotonic()
    with pytest.raises(TimeoutError):
        classify.post_with_retry("u", {}, {}, deadline=1.5)

    assert time.monotonic() - started < 1.5 + 0.3
    assert all(t <= 1.5 for t in given), given  # no try is given more than the budget


def test_each_try_gets_at_most_the_time_that_is_left(monkeypatch: pytest.MonkeyPatch) -> None:
    given: list[float] = []

    def refused(url: str, headers: dict, body: dict, timeout: float | None = None) -> dict:
        given.append(timeout)
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(classify, "http_post", refused)
    with pytest.raises(Exception):
        classify.post_with_retry("u", {}, {}, deadline=2.5)

    assert given[0] == pytest.approx(classify.QWEN_TRY_SECONDS if classify.QWEN_TRY_SECONDS < 2.5 else 2.5, abs=0.05)
    assert given == sorted(given, reverse=True), "the time given to each try only shrinks"


def test_a_refused_gateway_gives_up_within_the_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(classify, "http_post",
                        lambda url, headers, body, timeout=None: (_ for _ in ()).throw(urllib.error.URLError("refused")))
    started = time.monotonic()
    with pytest.raises(Exception):
        classify.post_with_retry("u", {}, {}, deadline=1.2)

    assert time.monotonic() - started < 1.2 + 0.3


def test_a_request_the_gateway_refuses_outright_is_not_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    tries: list[int] = []

    def bad_request(url: str, headers: dict, body: dict, timeout: float | None = None) -> dict:
        tries.append(1)
        raise http_error(400)

    monkeypatch.setattr(classify, "http_post", bad_request)
    with pytest.raises(urllib.error.HTTPError):
        classify.post_with_retry("u", {}, {}, deadline=5)

    assert len(tries) == 1


def test_the_upstream_status_reaches_the_caller(monkeypatch: pytest.MonkeyPatch) -> None:
    def rate_limited(prompt: str):
        raise http_error(429)

    email = EmailInput(email_id="email_001", from_email="a@b.example", subject="s", body="b")
    with pytest.raises(classify.ClassificationFailed) as failed:
        asyncio.run(classify.classify_email(email, model=rate_limited))

    assert failed.value.status_code == 429


def test_classify_answers_with_the_upstream_status_not_a_bare_502(monkeypatch: pytest.MonkeyPatch) -> None:
    async def rate_limited(email, second_opinion=None):
        raise classify.ClassificationFailed("HTTP Error 429", status_code=429)

    monkeypatch.setattr(app_module, "classify_email", rate_limited)
    got = TestClient(app_module.app).post("/classify", json={"email_id": "email_001", "from": "a@b.example",
                                                             "subject": "s", "body": "b"})

    assert got.status_code == 429


def test_an_error_without_an_http_status_is_still_a_502(monkeypatch: pytest.MonkeyPatch) -> None:
    def broken(prompt: str):
        raise ValueError("no JSON in the reply")

    email = EmailInput(email_id="email_001", from_email="a@b.example", subject="s", body="b")
    with pytest.raises(classify.ClassificationFailed) as failed:
        asyncio.run(classify.classify_email(email, model=broken))

    assert failed.value.status_code is None


def test_gemini_takes_over_classification_after_15_seconds_as_extraction_does() -> None:
    wiring = CLASSIFY_SOURCE[CLASSIFY_SOURCE.index("classification_model = with_fallback("):]
    wiring = wiring[:wiring.index(")\n") + 2]
    assert "first_timeout=QWEN_TRY_SECONDS" in wiring
    assert classify.QWEN_TRY_SECONDS == 15
