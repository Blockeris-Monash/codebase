"""Two things a public backend needs and this one did not have.

A REQUEST ID, so a failure a judge sees in the browser can be tied to the line
in the Render log that explains it. There were seventeen log calls and no way
to join any of them to a request.

A RATE LIMIT, because the URL is in a public repository, there is no auth, and
one `?live=true` press spends two Qwen calls. The daily quota is shared by the
whole team, so anyone who found the URL could exhaust the demo before judging
without meaning any harm.

Deliberately in-process and dependency-free: one Render instance serves this,
so a shared store would be a moving part with nothing to coordinate. That stops
being true the moment a second instance exists, which is noted rather than
guessed at.
"""
from __future__ import annotations

import logging
import time
import uuid
from collections import defaultdict, deque

from fastapi import Request
from fastapi.responses import JSONResponse

from backend.logging_setup import REQUEST_ID

log = logging.getLogger(__name__)

REQUEST_ID_HEADER = "X-Request-ID"
SERVER_ERROR = 500
# A monitor hits /health every few minutes; logging it buries the rest.
QUIET_PATHS = frozenset({"/health"})
WINDOW_SECONDS = 60.0
MAX_REQUESTS_PER_WINDOW = 30
TOO_MANY_REQUESTS = 429

# An allow-list, not a deny-list. The first version listed the cheap paths and
# limited everything else, which throttled exactly the wrong thing: the page
# polls /mailbox every 10 seconds, so five people behind one venue wifi spend
# 30 requests a minute on polling alone and the demo starts answering 429.
#
# What is worth protecting is the model quota the whole team shares. These are
# the routes that spend it; /mailbox, /reply, /health and the docs do not, and
# a new cheap route added later is not throttled by accident.
LIMITED_PATHS = frozenset({"/process-email", "/classify", "/translate",
                           "/extract-clean-compare"})

_seen: dict[str, deque[float]] = defaultdict(deque)


def caller(request: Request) -> str:
    """The forwarded address where there is one - Render sits behind a proxy,
    so request.client.host is the proxy for every caller alike."""
    forwarded = request.headers.get("x-forwarded-for", "")

    return forwarded.split(",")[0].strip() or (request.client.host if request.client else "unknown")


def is_over_limit(who: str, now: float) -> bool:
    """A sliding window. Old entries are dropped on every call, so the memory
    held is bounded by the callers seen inside one window."""
    recent = _seen[who]
    while recent and now - recent[0] > WINDOW_SECONDS:
        recent.popleft()
    if len(recent) >= MAX_REQUESTS_PER_WINDOW:
        return True
    recent.append(now)

    return False


async def tag_and_limit(request: Request, call_next):
    request_id = request.headers.get(REQUEST_ID_HEADER) or uuid.uuid4().hex[:12]
    # Set before anything else runs, so every line logged while handling this
    # request carries the same id the caller sees in the response header.
    REQUEST_ID.set(request_id)
    started = time.monotonic()

    if request.url.path in LIMITED_PATHS and is_over_limit(caller(request), time.monotonic()):
        log.warning("rate limited %s on %s [%s]", caller(request), request.url.path, request_id)
        return JSONResponse(
            status_code=TOO_MANY_REQUESTS,
            content={"detail": f"More than {MAX_REQUESTS_PER_WINDOW} requests in "
                               f"{WINDOW_SECONDS:g}s. Wait a moment and try again."},
            headers={REQUEST_ID_HEADER: request_id})

    response = await call_next(request)
    response.headers[REQUEST_ID_HEADER] = request_id

    # One line per request, with how long it took. /health is left out: the
    # uptime monitor calls it every few minutes and would bury everything else.
    if request.url.path not in QUIET_PATHS:
        elapsed = time.monotonic() - started
        level = logging.WARNING if response.status_code >= SERVER_ERROR else logging.INFO
        log.log(level, "%s %s -> %s in %.2fs",
                request.method, request.url.path, response.status_code, elapsed)

    return response
