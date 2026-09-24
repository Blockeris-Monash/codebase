"""The health check the uptime monitor calls. It sends HEAD, not GET, and a 405
there shows the backend as down while it is up."""
from __future__ import annotations

from fastapi.testclient import TestClient

from backend.app import app


def test_health_answers_get() -> None:
    response = TestClient(app).get("/health")

    assert response.status_code == 200 and response.json() == {"status": "ok"}


def test_health_answers_head_as_the_uptime_monitor_sends_it() -> None:
    assert TestClient(app).head("/health").status_code == 200
