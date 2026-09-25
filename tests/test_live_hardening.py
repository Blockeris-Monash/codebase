"""What a public backend needs to survive being public during judging.

The rules say the deployment must be "publicly accessible and functional during
the judging period". The URL is in a public repository, there is no auth, and
one `?live=true` press spends two Qwen calls against a quota the whole team
shares - so anyone who found it could exhaust the demo before judging without
meaning any harm. And with seventeen log calls and no correlation id, a failure
a judge saw in the browser could not be tied to the line that explained it.
"""
from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from backend import middleware
from backend.app import app
from backend.middleware import (
    LIMITED_PATHS, MAX_REQUESTS_PER_WINDOW, REQUEST_ID_HEADER, is_over_limit,
)


@pytest.fixture(autouse=True)
def clean_window():
    middleware._seen.clear()
    yield
    middleware._seen.clear()


def test_every_answer_carries_a_request_id() -> None:
    response = TestClient(app).get("/health")

    assert response.headers.get(REQUEST_ID_HEADER)


def test_a_caller_supplied_id_is_kept_so_a_trace_survives_the_hop() -> None:
    response = TestClient(app).get("/health", headers={REQUEST_ID_HEADER: "abc123"})

    assert response.headers[REQUEST_ID_HEADER] == "abc123"


def test_the_health_check_is_never_throttled() -> None:
    """Uptime Robot is what keeps Render awake. Throttling it puts the service
    to sleep, which is the opposite of the point."""
    assert "/health" not in LIMITED_PATHS
    client = TestClient(app)

    codes = {client.get("/health").status_code for _ in range(MAX_REQUESTS_PER_WINDOW + 5)}

    assert codes == {200}


def test_a_caller_past_the_ceiling_is_refused() -> None:
    now = time.monotonic()
    over = [is_over_limit("1.2.3.4", now) for _ in range(MAX_REQUESTS_PER_WINDOW + 1)]

    assert over[:MAX_REQUESTS_PER_WINDOW] == [False] * MAX_REQUESTS_PER_WINDOW
    assert over[-1] is True


def test_one_caller_cannot_throttle_another() -> None:
    now = time.monotonic()
    for _ in range(MAX_REQUESTS_PER_WINDOW):
        is_over_limit("1.1.1.1", now)

    assert is_over_limit("2.2.2.2", now) is False


def test_the_window_slides_rather_than_locking_someone_out() -> None:
    start = time.monotonic()
    for _ in range(MAX_REQUESTS_PER_WINDOW):
        is_over_limit("3.3.3.3", start)

    assert is_over_limit("3.3.3.3", start) is True
    assert is_over_limit("3.3.3.3", start + middleware.WINDOW_SECONDS + 1) is False


def test_the_memory_held_is_bounded_by_one_window() -> None:
    """Without the eviction this is a dict that only ever grows."""
    start = time.monotonic()
    for _ in range(MAX_REQUESTS_PER_WINDOW):
        is_over_limit("4.4.4.4", start)
    is_over_limit("4.4.4.4", start + middleware.WINDOW_SECONDS + 1)

    assert len(middleware._seen["4.4.4.4"]) == 1


def fake_request(headers: dict[str, str], path: str = "/process-email"):
    from starlette.datastructures import Headers, URL

    class FakeRequest:
        pass

    request = FakeRequest()
    request.headers = Headers(headers)
    request.client = None
    request.url = URL(f"https://example.test{path}")

    return request


def test_cloudflares_connecting_address_is_used_not_the_forwarded_chain() -> None:
    """Render sits behind Cloudflare, which writes cf-connecting-ip itself."""
    from backend.middleware import caller

    request = fake_request({"cf-connecting-ip": "9.9.9.9", "x-forwarded-for": "6.6.6.6, 9.9.9.9"})

    assert caller(request) == "9.9.9.9"


def test_without_cloudflare_the_address_the_proxy_appended_is_used() -> None:
    """The leftmost X-Forwarded-For entry is whatever the caller wrote (#147 A2)."""
    from backend.middleware import caller

    assert caller(fake_request({"x-forwarded-for": "6.6.6.6, 9.9.9.9"})) == "9.9.9.9"


def test_rotating_a_forged_forwarded_header_does_not_reset_the_limit() -> None:
    from backend.middleware import caller

    start = time.monotonic()
    answers = [is_over_limit(caller(fake_request({"x-forwarded-for": f"6.6.6.{n}, 8.8.8.8"})), start)
               for n in range(MAX_REQUESTS_PER_WINDOW + 1)]

    assert answers[-1] is True


def test_the_mailbox_is_limited_per_signed_in_person() -> None:
    from backend.middleware import MAX_MAILBOX_REQUESTS_PER_WINDOW, limited_caller

    start = time.monotonic()
    same_person = fake_request({"authorization": "Bearer token-a", "cf-connecting-ip": "1.2.3.4"}, "/mailbox")
    other_person = fake_request({"authorization": "Bearer token-b", "cf-connecting-ip": "1.2.3.4"}, "/mailbox")
    over = lambda request: is_over_limit(limited_caller(request).who, start, limited_caller(request).limit)
    for _ in range(MAX_MAILBOX_REQUESTS_PER_WINDOW):
        over(same_person)

    assert over(same_person) is True
    assert over(other_person) is False


def test_a_flood_of_made_up_callers_is_forgotten_once_idle(monkeypatch) -> None:
    monkeypatch.setattr(middleware, "_seen", middleware.defaultdict(middleware.deque))
    monkeypatch.setattr(middleware, "MAX_TRACKED_CALLERS", 100)
    start = time.monotonic()
    for n in range(150):
        is_over_limit(f"forged-{n}", start)

    is_over_limit("later", start + middleware.WINDOW_SECONDS + 1)

    assert len(middleware._seen) <= 101


@pytest.mark.parametrize("path,model", [
    ("/health", "Health"), ("/process-email", "ProcessedEmail"),
    ("/classify", "ClassificationResult"), ("/translate", "TranslateResponse"),
    ("/extract-clean-compare", "ComparisonResult"),
])
def test_every_route_declares_the_shape_it_answers_with(path: str, model: str) -> None:
    """`/process-email` returned Dict[str, Any] - the shape was unchecked, and
    the five people integrating against it had only the source to go on."""
    route = next(r for r in app.routes if getattr(r, "path", None) == path)

    assert getattr(route.response_model, "__name__", None) == model


def test_the_dependencies_are_pinned_not_floated() -> None:
    """A release between a green CI run and judging could change what Render
    builds with nothing here going red, because CI floats too."""
    from pathlib import Path
    lines = [l.strip() for l in (Path(__file__).resolve().parents[1] / "requirements.txt")
             .read_text(encoding="utf-8").splitlines()
             if l.strip() and not l.startswith("#")]

    assert lines, "requirements.txt is empty"
    assert all("==" in l for l in lines), [l for l in lines if "==" not in l]


def test_the_browser_library_is_pinned_too() -> None:
    """`@2` floats: a release during judging would change the code running in a
    judge's browser with nothing in this repository changing."""
    import re
    from pathlib import Path
    index = (Path(__file__).resolve().parents[1] / "frontend/index.html").read_text(encoding="utf-8")

    assert not re.search(r"supabase-js@\d+/", index), "still on a floating major"
    assert re.search(r"supabase-js@\d+\.\d+\.\d+/", index)


def test_polling_the_mailbox_is_not_throttled() -> None:
    """The page polls /mailbox every 10 seconds. Five people behind one venue
    wifi share a public address, so polling alone is 30 requests a minute -
    the whole ceiling - and the demo would answer 429 during judging. A repeat
    poll returns a saved result and costs no model call, so there is nothing
    to protect there."""
    assert "/mailbox" not in LIMITED_PATHS
    assert "/reply" not in LIMITED_PATHS


def test_the_routes_that_spend_model_quota_are_the_ones_limited() -> None:
    """That quota is shared by the whole team and the URL is public."""
    assert LIMITED_PATHS == {"/process-email", "/classify", "/translate",
                             "/extract-clean-compare", "/check-files", "/draft-reply"}
