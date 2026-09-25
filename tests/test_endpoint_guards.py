"""Guards on what any caller can send, found by the endpoint review in #147.

Nothing capped a request body, a 422 echoed the whole input back, a caller's
X-Request-ID went into every log line as written, one mailbox's checks queued ahead
of every other's, and the limiter's idle sweep rescanned a full table on every request.
"""
from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from backend import middleware
from backend.app import app


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


def test_a_body_past_the_cap_is_refused_before_it_is_read(client: TestClient) -> None:
    oversize = str(middleware.MAX_BODY_BYTES + 1)

    response = client.post("/classify", content=b"{}", headers={"content-length": oversize,
                                                                  "content-type": "application/json"})

    assert response.status_code == middleware.PAYLOAD_TOO_LARGE


def test_an_upload_has_room_for_two_five_megabyte_files() -> None:
    two_files_as_base64_json = 2 * 5 * 1024 * 1024 * 4 // 3 + 1000

    assert two_files_as_base64_json < middleware.MAX_UPLOAD_BYTES


def test_an_invalid_request_is_described_without_echoing_it(client: TestClient) -> None:
    marker = "ECHO-ME-" * 100

    response = client.post("/classify", json={"email_id": marker})

    assert response.status_code == 422
    assert marker not in response.text


@pytest.mark.parametrize(("offered", "is_kept"), [("abc-123", True), ("x] GET /admin -> 200", False),
                                                  ("a" * 65, False)])
def test_a_callers_request_id_is_kept_only_when_it_looks_like_one(client: TestClient, offered: str,
                                                                   is_kept: bool) -> None:
    response = client.get("/health", headers={"X-Request-ID": offered})

    assert (response.headers["X-Request-ID"] == offered) is is_kept


def test_the_mailbox_budget_is_per_token_whatever_the_spacing() -> None:
    from backend.middleware import mailbox_caller
    from starlette.datastructures import Headers

    class FakeRequest:
        pass

    one, other = FakeRequest(), FakeRequest()
    one.headers = Headers({"authorization": "Bearer token-a"})
    other.headers = Headers({"authorization": "bearer   token-a "})

    assert mailbox_caller(one) == mailbox_caller(other)


def test_the_idle_sweep_runs_at_most_once_a_window(monkeypatch) -> None:
    now = time.monotonic()
    monkeypatch.setattr(middleware, "_last_sweep", now)
    monkeypatch.setattr(middleware, "_seen", middleware.defaultdict(middleware.deque, {"idle": middleware.deque()}))

    middleware.forget_idle_callers(now + 1)

    assert "idle" in middleware._seen


@pytest.mark.parametrize("subject", ["Hello\x0bBcc: x@y.z", "Hello Bcc: x@y.z"])
def test_a_reply_subject_with_any_line_break_is_refused(client: TestClient, subject: str) -> None:
    response = client.post("/reply", json={"email_id": "gmail_abcdef12", "to": "a@b.com",
                                           "subject": subject, "body": "hi"},
                           headers={"Authorization": "Bearer t"})

    assert response.status_code == 422
