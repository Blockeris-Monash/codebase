"""Technical reports: the AI needed more than one try, or never answered.

One row in `reports` per email and step - sorting an email, reading its SI,
reading its BL, drafting a reply - filed when that step took more than one model
call or ended with no answer at all. The admin queue (frontend/admin.html) lists
them under Automatic, most tries first, because the step that struggled most is
the one to read first.

Every model call made through with_fallback is recorded, but only while a step is
being watched (`watching` below). A call outside one - a translation, a batch
run - records nothing and files nothing.

Written with the Supabase service-role key. A technical report has no user, so no
signed-in session could file one, and migration 0004 lets only admins read them.
The key is a secret held on the server, never on the page. Without SUPABASE_URL
and SUPABASE_SERVICE_ROLE_KEY nothing is written, so local runs and CI behave
exactly as before.

Filing must never slow down or break the check it describes, so the write runs on
a background thread and any failure there is logged and dropped.
"""
from __future__ import annotations

import logging
import os
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

import httpx

log = logging.getLogger(__name__)

ANSWERED = "answered"
KIND = "technical"
MAX_RESULT_CHARS = 300  # a provider's error can be a page of HTML
TIMEOUT_SECONDS = 10.0
# Tests put a fake Supabase here; in service it stays None and httpx goes to the network.
TRANSPORT: Optional[httpx.BaseTransport] = None


@dataclass
class Attempt:
    model: str
    result: str  # ANSWERED, or why it did not answer
    seconds: float


@dataclass
class Step:
    name: str
    email_id: Optional[str]
    if_no_answer: str  # what happens to the email when no model answers
    attempts: list[Attempt] = field(default_factory=list)
    note: Optional[tuple[str, str]] = None  # (title, outcome) when the step explains itself


# A ContextVar, not a global: SI and BL are read at the same time for one email,
# and several emails are checked at once. asyncio.to_thread copies the context,
# so a model call on a worker thread still lands in the step that asked for it.
_step: ContextVar[Optional[Step]] = ContextVar("technical_report_step", default=None)
_writer = ThreadPoolExecutor(max_workers=1, thread_name_prefix="technical-reports")


def record(model: str, result: str, seconds: float) -> None:
    """One model call, kept for the step being watched. Outside one, nothing."""
    step = _step.get()
    if step is not None:
        step.attempts.append(Attempt(model, result[:MAX_RESULT_CHARS], round(seconds, 1)))


def answered_by() -> Optional[str]:
    """The model whose answer the watched step is using so far, or None."""
    step = _step.get()
    answered = [a.model for a in step.attempts if a.result == ANSWERED] if step else []

    return answered[-1] if answered else None


def note(title: str, outcome: str) -> None:
    """Say what the watched step decided, in place of the default wording. A step
    that explains itself is always reported: the critic uses this for every
    second opinion it asks for, agreed or not."""
    step = _step.get()
    if step is not None:
        step.note = (title, outcome)


@contextmanager
def watching(name: str, email_id: Optional[str], if_no_answer: str) -> Iterator[None]:
    """Collect the model calls made inside, and file one report if they struggled."""
    step = Step(name, email_id, if_no_answer)
    token = _step.set(step)
    try:
        yield
    finally:
        _step.reset(token)
        if struggled(step):
            file(as_row(step))


def struggled(step: Step) -> bool:
    return (step.note is not None or len(step.attempts) > 1
            or bool(step.attempts and step.attempts[-1].result != ANSWERED))


def as_row(step: Step) -> dict[str, Any]:
    tries = len(step.attempts)
    if step.note:
        title, outcome = f"{step.name}: {step.note[0]}", step.note[1]
    elif step.attempts[-1].result == ANSWERED:
        title = f"{step.name}: answered on try {tries}, by {step.attempts[-1].model}"
        outcome = f"Answered by {step.attempts[-1].model}, so the check went ahead."
    else:
        title = f"{step.name}: no AI answer after {tries} {'try' if tries == 1 else 'tries'}"
        outcome = step.if_no_answer
    lines = [f"{n}. {a.model}: {a.result} ({a.seconds:g} s)" for n, a in enumerate(step.attempts, 1)]

    return {
        "kind": KIND,
        "email_ref": step.email_id,
        "title": title,
        "detail": outcome + "\n\n" + "\n".join(lines),
        "context": {"step": step.name, "tries": tries, "outcome": outcome,
                    "attempts": [asdict(a) for a in step.attempts]},
    }


def file(row: dict[str, Any]) -> None:
    """Log the report, and queue it for the database when one is configured."""
    log.warning("technical report: %s [%s]", row["title"], row["email_ref"] or "no email")
    url, key = os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if url and key:
        _writer.submit(send, url.rstrip("/"), key, row)


def headers_for(key: str) -> dict[str, str]:
    """A secret key (sb_secret_...) goes in `apikey` alone: it is not a JWT, and
    sent as `Authorization: Bearer` Supabase rejects it as an invalid JWT. A
    legacy service_role key is a JWT, and goes in both, as Supabase's own clients send it."""
    headers = {"apikey": key, "Prefer": "return=minimal"}
    if not key.startswith("sb_"):
        headers["Authorization"] = f"Bearer {key}"

    return headers


def send(url: str, key: str, row: dict[str, Any]) -> None:
    try:
        with httpx.Client(transport=TRANSPORT, timeout=TIMEOUT_SECONDS) as client:
            response = client.post(f"{url}/rest/v1/reports", json=row, headers=headers_for(key))
        response.raise_for_status()
    except Exception as error:  # the network, Supabase or the key: none of them may reach the check
        log.warning("technical report not saved (%s): %s", error, row["title"])


def settle(timeout: float = 5.0) -> None:
    """Wait until every report queued so far has been written. For tests."""
    _writer.submit(lambda: None).result(timeout=timeout)
