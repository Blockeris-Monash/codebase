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
    MAX_REQUESTS_PER_WINDOW, REQUEST_ID_HEADER, UNLIMITED_PATHS, is_over_limit,
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
    assert "/health" in UNLIMITED_PATHS
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


def test_the_forwarded_address_is_used_not_the_proxy() -> None:
    """Render sits behind a proxy, so request.client.host is the same for every
    caller - limiting on it would throttle everyone together."""
    from starlette.datastructures import Headers
    from backend.middleware import caller

    class FakeRequest:
        headers = Headers({"x-forwarded-for": "9.9.9.9, 10.0.0.1"})
        client = None

    assert caller(FakeRequest()) == "9.9.9.9"


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
