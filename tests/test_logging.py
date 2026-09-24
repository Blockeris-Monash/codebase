"""The service's log lines have to survive to somewhere a person can read them.

Nothing configured logging, so `logging.getLogger(__name__)` fell back to
Python's last resort: WARNING and above, to stderr, with no timestamp, no logger
name and no request id. Every `log.info(...)` already written in the backend was
discarded, and a warning that did appear could not be placed in time or tied to
the request a judge saw fail.
"""
from __future__ import annotations

import logging

import pytest
from fastapi.testclient import TestClient

from backend.app import app
from backend.logging_setup import NO_REQUEST, NOISY, configure


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_an_info_line_is_not_thrown_away() -> None:
    """The whole point. Importing backend.app configures logging, so INFO from
    our own loggers reaches a handler."""
    configure()

    assert logging.getLogger("backend.app").isEnabledFor(logging.INFO)


def test_exactly_one_handler_however_many_times_it_is_called() -> None:
    """configure() runs at import, and a test or a second entry point can call
    it again. Adding a handler each time prints everything twice, then three
    times, which is how a log becomes unreadable."""
    before = configure()
    again = configure()
    ours = [h for h in logging.getLogger().handlers if getattr(h, "_ship_happens", False)]

    assert before is again
    assert len(ours) == 1


def test_every_line_carries_the_request_id(client: TestClient, caplog) -> None:
    """The response header and the log line have to name the same request, or a
    failure a judge reports cannot be found in the log."""
    with caplog.at_level(logging.INFO):
        response = client.get("/does-not-exist", headers={"X-Request-ID": "judge-saw-this"})

    assert response.headers["X-Request-ID"] == "judge-saw-this"
    assert any("judge-saw-this" in record.getMessage() or
               getattr(record, "request_id", "") == "judge-saw-this"
               for record in caplog.records)


def test_an_id_is_invented_when_the_caller_does_not_send_one(client: TestClient) -> None:
    response = client.get("/does-not-exist")

    assert response.headers["X-Request-ID"]
    assert response.headers["X-Request-ID"] != NO_REQUEST


def test_a_line_logged_outside_a_request_still_formats() -> None:
    """A batch run or a startup line has no request. The filter has to supply
    something rather than raise KeyError inside the formatter, which would turn
    a log line into a crash."""
    handler = configure()
    record = logging.LogRecord("t", logging.INFO, __file__, 1, "hello", None, None)
    for log_filter in handler.filters:
        log_filter.filter(record)

    assert handler.format(record).endswith("hello")
    assert f"[{NO_REQUEST}]" in handler.format(record)


def test_health_is_not_logged(client: TestClient, caplog) -> None:
    """The uptime monitor calls it every few minutes. Logging it buries every
    line that matters under a wall of identical ones."""
    with caplog.at_level(logging.INFO, logger="backend.middleware"):
        client.get("/health")

    assert [r for r in caplog.records if "/health" in r.getMessage()] == []


@pytest.mark.parametrize("status,expected", [(200, logging.INFO), (500, logging.WARNING)])
def test_a_server_error_is_logged_louder_than_a_normal_reply(status, expected, caplog) -> None:
    """A 500 read at INFO, in the same column as every healthy request, is a 500
    nobody sees. The middleware is driven directly so the status is the only
    thing that varies."""
    import asyncio

    from starlette.responses import PlainTextResponse
    from starlette.requests import Request

    from backend.middleware import tag_and_limit

    scope = {"type": "http", "method": "GET", "path": "/process-email",
             "headers": [], "query_string": b"", "root_path": "", "app": app}

    async def call_next(_):
        return PlainTextResponse("", status_code=status)

    with caplog.at_level(logging.INFO, logger="backend.middleware"):
        asyncio.run(tag_and_limit(Request(scope), call_next))

    lines = [r for r in caplog.records if "/process-email" in r.getMessage()]
    assert len(lines) == 1
    assert lines[0].levelno == expected


def test_the_libraries_that_log_every_call_are_quietened() -> None:
    """httpx logs a line per outbound request. At INFO that is a transcript of
    every Gmail and model call sitting on top of our own lines."""
    configure()
    for name in NOISY:
        assert logging.getLogger(name).level == logging.WARNING, name


def test_a_bad_level_in_the_environment_does_not_silence_everything(monkeypatch) -> None:
    """`logging.getLevelName` answers "Level NONSENSE" for anything it does not
    know, and setting that as a level silently stops all logging - the exact
    failure this module exists to prevent."""
    from backend import logging_setup

    monkeypatch.setenv(logging_setup.LEVEL_VAR, "NONSENSE")

    assert logging_setup._level() == logging.INFO
