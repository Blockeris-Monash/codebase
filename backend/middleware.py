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

import hashlib
import logging
import re
import time
import uuid
from collections import defaultdict, deque
from typing import NamedTuple

from fastapi import Request
from fastapi.responses import JSONResponse

from backend import reports
from backend.logging_setup import REQUEST_ID

log = logging.getLogger(__name__)

REQUEST_ID_HEADER = "X-Request-ID"
SERVER_ERROR = 500
# A monitor hits /health every few minutes; logging it buries the rest.
QUIET_PATHS = frozenset({"/health"})
WINDOW_SECONDS = 60.0
MAX_REQUESTS_PER_WINDOW = 30
TOO_MANY_REQUESTS = 429
PAYLOAD_TOO_LARGE = 413
SAFE_REQUEST_ID = re.compile(r"[A-Za-z0-9._-]{1,64}")
# An upload is two files of up to 5 MB as base64 in JSON; everything else is an email.
UPLOAD_PATH = "/check-files"
MAX_UPLOAD_BYTES = 17_000_000
MAX_BODY_BYTES = 2_000_000

# An allow-list, not a deny-list. The first version listed the cheap paths and
# limited everything else, which throttled exactly the wrong thing: the page
# polls /mailbox every 10 seconds, so five people behind one venue wifi spend
# 30 requests a minute on polling alone and the demo starts answering 429.
#
# What is worth protecting is the model quota the whole team shares. These are
# the routes that spend it; /reply, /health and the docs do not, and a new cheap
# route added later is not throttled by accident. /mailbox does spend it (a poll
# starts checks on new mail) and has its own budget below.
LIMITED_PATHS = frozenset({"/process-email", "/classify", "/translate",
                           "/extract-clean-compare", "/check-files", "/draft-reply",
                           "/refine"})

# /mailbox is polled every 10 s per open tab, so it gets its own budget, and it is
# counted per signed-in person rather than per address: a venue's wifi puts everyone
# behind one address. Each poll can start model checks on new mail, and billing is on.
MAILBOX_PATH = "/mailbox"
MAX_MAILBOX_REQUESTS_PER_WINDOW = 20

# Cloudflare sits in front of Render and writes this header itself, replacing any
# value the caller sent, so unlike the left of X-Forwarded-For it cannot be forged.
CONNECTING_IP_HEADER = "cf-connecting-ip"
# Past this many tracked callers, the ones idle for a whole window are forgotten, so
# a stream of made-up callers cannot grow the table without end.
MAX_TRACKED_CALLERS = 10_000
FLOOD_FACTOR = 5

_seen: dict[str, deque[float]] = defaultdict(deque)


def caller(request: Request) -> str:
    """Who is calling, as far as the proxies in front can vouch for it.

    Render sits behind Cloudflare, so request.client.host is a proxy for every
    caller alike. The leftmost X-Forwarded-For entry is whatever the caller wrote,
    so changing it on every request used to dodge the limit entirely. The rightmost
    entry is the one the nearest proxy appended, and is the fallback."""
    connecting = request.headers.get(CONNECTING_IP_HEADER, "").strip()
    if connecting:
        return connecting
    forwarded = request.headers.get("x-forwarded-for", "")

    return forwarded.split(",")[-1].strip() or (request.client.host if request.client else "unknown")


def mailbox_caller(request: Request) -> str:
    """One budget per Google token, hashed so no token is held in memory. The token itself,
    not the raw header, so spacing or the case of "Bearer" cannot open a second budget."""
    token = request.headers.get("authorization", "").strip().removeprefix("Bearer").removeprefix("bearer").strip()

    return "mailbox:" + hashlib.sha256(token.encode()).hexdigest()[:16]


def caller_shape(address: str) -> str:
    """Enough of an address to tell one network from another, never the whole of it."""
    if ":" in address:
        return ":".join(address.split(":")[:3]) + ":x"
    if address.count(".") == 3:
        return address.rsplit(".", 1)[0] + ".x"

    return "unknown"


_last_sweep = 0.0


def forget_idle_callers(now: float) -> None:
    """Drop every caller with nothing inside the window - at most once a window, so a
    table full of active callers is not rescanned on every request. A table still past
    the hard cap after that is a flood of made-up callers, and is emptied."""
    global _last_sweep
    if now - _last_sweep < WINDOW_SECONDS:
        return
    _last_sweep = now
    idle = [who for who, recent in _seen.items() if not recent or now - recent[-1] > WINDOW_SECONDS]
    for who in idle:
        del _seen[who]
    if len(_seen) > MAX_TRACKED_CALLERS * FLOOD_FACTOR:
        _seen.clear()


def is_over_limit(who: str, now: float, limit: int = MAX_REQUESTS_PER_WINDOW) -> bool:
    """A sliding window. Old entries are dropped on every call, and idle callers
    once the table is large, so the memory held stays bounded."""
    if len(_seen) > MAX_TRACKED_CALLERS:
        forget_idle_callers(now)
    recent = _seen[who]
    while recent and now - recent[0] > WINDOW_SECONDS:
        recent.popleft()
    if len(recent) >= limit:
        return True
    recent.append(now)

    return False


class Budget(NamedTuple):
    """Whose window a request counts against, and how many it may hold."""
    who: str
    limit: int


def is_too_large(request: Request) -> bool:
    """Past what any real request carries. Nothing capped the body, so a 50 MB post was
    read whole, parsed, and echoed back in the 422 (#147). Chunked bodies with no length
    are not covered; Render's proxy caps those."""
    cap = MAX_UPLOAD_BYTES if request.url.path == UPLOAD_PATH else MAX_BODY_BYTES
    declared = request.headers.get("content-length", "")

    return declared.isdigit() and int(declared) > cap


def limited_caller(request: Request) -> Budget | None:
    """The budget this request counts against, or None for a route that spends nothing."""
    if request.url.path == MAILBOX_PATH:
        return Budget(mailbox_caller(request), MAX_MAILBOX_REQUESTS_PER_WINDOW)
    if request.url.path in LIMITED_PATHS:
        return Budget(caller(request), MAX_REQUESTS_PER_WINDOW)

    return None


async def tag_and_limit(request: Request, call_next):
    # A caller's own id only when it looks like one: it is written into every log line.
    offered = request.headers.get(REQUEST_ID_HEADER, "")
    request_id = offered if SAFE_REQUEST_ID.fullmatch(offered) else uuid.uuid4().hex[:12]
    # Set before anything else runs, so every line logged while handling this
    # request carries the same id the caller sees in the response header.
    REQUEST_ID.set(request_id)
    started = time.monotonic()

    if is_too_large(request):
        return JSONResponse(status_code=PAYLOAD_TOO_LARGE, content={"detail": "Request too large."},
                            headers={REQUEST_ID_HEADER: request_id})

    budget = limited_caller(request)
    if budget is not None and is_over_limit(budget.who, time.monotonic(), budget.limit):
        log.warning("rate limited %s on %s [%s]", caller(request), request.url.path, request_id)
        # A technical report for the admin queue; reports holds back the repeats (#114).
        reports.file({"kind": reports.KIND, "email_ref": None, "title": "Rate limited",
                      "detail": f"A caller from {caller_shape(caller(request))} went past "
                                f"{budget.limit} requests in {WINDOW_SECONDS:g}s on "
                                f"{request.url.path} and was refused. Request {request_id} is in the log.",
                      "context": {"step": "Rate limit", "path": request.url.path,
                                  "caller": caller_shape(caller(request)), "request_id": request_id}})
        return JSONResponse(
            status_code=TOO_MANY_REQUESTS,
            content={"detail": f"More than {budget.limit} requests in "
                               f"{WINDOW_SECONDS:g}s. Wait a moment and try again."},
            headers={REQUEST_ID_HEADER: request_id})

    response = await call_next(request)
    response.headers[REQUEST_ID_HEADER] = request_id

    # One line per request, with how long it took. /health is left out: the
    # uptime monitor calls it every few minutes and would bury everything else.
    if request.url.path not in QUIET_PATHS:
        elapsed = time.monotonic() - started
        level = logging.WARNING if response.status_code >= SERVER_ERROR else logging.INFO
        # The caller's network, never the whole address: after a deploy this line shows
        # whether callers really differ, i.e. that cf-connecting-ip is reaching us.
        log.log(level, "%s %s -> %s in %.2fs from %s",
                request.method, request.url.path, response.status_code, elapsed,
                caller_shape(caller(request)))

    return response
