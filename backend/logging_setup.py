"""One logging configuration for the service, so the log lines already in the
code actually reach the console.

Nothing configured logging. `logging.getLogger(__name__)` with no handler falls
back to Python's last resort, which prints WARNING and above to stderr with no
timestamp, no logger name and no formatting at all - so every `log.info(...)`
in the backend was discarded, and the warnings that did survive could not be
placed in time or tied to a request.

That matters most in the one situation it was written for: something goes wrong
while a judge is looking at the deployed app, and the only evidence is whatever
Render's log viewer kept.

Every line carries the request id that the response also carries in
`X-Request-ID`, so a failure seen in a browser can be found in the log. The id
travels in a ContextVar rather than an argument, because the alternative is
threading it through every call between the middleware and the thing that fails.
"""
from __future__ import annotations

import logging
import os
import sys
from contextvars import ContextVar

# "-" rather than "" so a line logged outside a request still lines up in the
# column, which matters when reading a log as text rather than as JSON.
NO_REQUEST = "-"
REQUEST_ID: ContextVar[str] = ContextVar("request_id", default=NO_REQUEST)

LEVEL_VAR = "LOG_LEVEL"
DEFAULT_LEVEL = "INFO"
FORMAT = "%(asctime)s %(levelname)-7s %(name)s [%(request_id)s] %(message)s"
TIME_FORMAT = "%Y-%m-%d %H:%M:%S"

# Render captures stderr; stdout is buffered differently in some runtimes and a
# crash can lose the last lines, which are the interesting ones.
STREAM = sys.stderr

# Libraries that log one line per outbound call. At INFO they bury our own lines
# under a transcript of every Gmail and model request, which is the opposite of
# what this is for. Their warnings and errors still come through.
NOISY = ("httpx", "httpx2", "httpcore", "hpack", "urllib3")


class RequestIdFilter(logging.Filter):
    """Puts the current request id on every record, including records from
    libraries that know nothing about it."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = REQUEST_ID.get()
        return True


def _level() -> int:
    name = (os.environ.get(LEVEL_VAR) or DEFAULT_LEVEL).upper()
    resolved = logging.getLevelName(name)

    # getLevelName returns the string "Level XYZ" for anything it does not know,
    # and silently logging nothing because of a typo in an environment variable
    # is the failure this whole module exists to prevent.
    return resolved if isinstance(resolved, int) else logging.INFO


def configure() -> logging.Handler:
    """Attach one handler to the root logger. Safe to call more than once: a
    second call re-uses the handler rather than printing everything twice."""
    root = logging.getLogger()
    for existing in root.handlers:
        if getattr(existing, "_ship_happens", False):
            root.setLevel(_level())
            return existing

    handler = logging.StreamHandler(STREAM)
    handler.setFormatter(logging.Formatter(FORMAT, datefmt=TIME_FORMAT))
    handler.addFilter(RequestIdFilter())
    handler._ship_happens = True                      # type: ignore[attr-defined]

    root.addHandler(handler)
    root.setLevel(_level())
    for name in NOISY:
        logging.getLogger(name).setLevel(logging.WARNING)

    return handler
