"""Technical reports: when the AI needs more than one try, or never answers, the
admin queue hears about it, most tries first.

The models and Supabase are fakes, so these run offline and fast."""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from pathlib import Path

import httpx
import pytest

from backend import reports
from backend.contracts import ExtractedField
from backend.extract.ai import AiExtractor
from backend.extract.fallback import with_fallback

ROOT = Path(__file__).resolve().parents[1]
ADMIN = (ROOT / "frontend" / "admin.html").read_text(encoding="utf-8")
STORE = (ROOT / "frontend" / "store.js").read_text(encoding="utf-8")

EMAIL = "gmail_18f2a"
SUPABASE_URL = "https://project.supabase.test"
SERVICE_KEY = "service-role-key"
FIELDS = ("shipper", "consignee", "notify_party", "port_of_loading",
          "port_of_discharge", "container_count", "gross_weight_kg")


def answer(text: str) -> dict[str, ExtractedField]:
    return {name: {"present": True, "label_seen": name, "raw": "ACME"} for name in FIELDS}


def broken(text: str) -> dict[str, ExtractedField]:
    raise RuntimeError("gateway unreachable")


def use_database(monkeypatch: pytest.MonkeyPatch, handler) -> None:
    monkeypatch.setenv("SUPABASE_URL", SUPABASE_URL)
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", SERVICE_KEY)
    monkeypatch.setattr(reports, "TRANSPORT", httpx.MockTransport(handler))


@pytest.fixture
def queue(monkeypatch: pytest.MonkeyPatch):
    """A fake Supabase that accepts every report: (request, row) for each one posted."""
    posted: list[tuple[httpx.Request, dict]] = []

    def accept(request: httpx.Request) -> httpx.Response:
        posted.append((request, json.loads(request.content)))
        return httpx.Response(201)

    use_database(monkeypatch, accept)
    yield posted
    reports.settle()  # nothing still queued may outlive the fake it was meant for


def filed(queue: list[tuple[httpx.Request, dict]]) -> list[dict]:
    reports.settle()
    return [row for _, row in queue]


def only(queue: list[tuple[httpx.Request, dict]]) -> dict:
    rows = filed(queue)
    assert len(rows) == 1, rows
    return rows[0]


def backup_step() -> None:
    """Qwen fails, Gemini answers: the commonest thing worth reporting."""
    with reports.watching("Classification", EMAIL, "The email could not be sorted."):
        with_fallback(broken, answer)("text")


# --- when a report is filed --------------------------------------------------

def test_a_step_answered_on_the_first_try_files_nothing(queue) -> None:
    with reports.watching("Classification", EMAIL, "not sorted"):
        with_fallback(answer, broken)("text")

    assert filed(queue) == []


def test_calls_outside_a_watched_step_file_nothing(queue) -> None:
    """A translation or a batch run is not watched: its retries are not an email's."""
    with_fallback(broken, answer)("text")

    assert filed(queue) == []


def test_a_backup_answer_files_one_report_with_both_tries(queue) -> None:
    backup_step()

    row = only(queue)
    assert row["kind"] == "technical" and row["email_ref"] == EMAIL
    assert row["title"] == "Classification: answered on try 2, by Gemini"
    assert row["context"]["tries"] == 2
    assert [a["model"] for a in row["context"]["attempts"]] == ["Qwen", "Gemini"]
    assert [a["result"] for a in row["context"]["attempts"]] == ["gateway unreachable", "answered"]


def test_a_stalled_first_model_is_reported_as_no_answer_in_time(queue) -> None:
    def stalled(text: str) -> dict[str, ExtractedField]:
        time.sleep(2)
        return answer(text)

    with reports.watching("Classification", EMAIL, "not sorted"):
        with_fallback(stalled, answer, first_timeout=0.2)("text")

    assert only(queue)["context"]["attempts"][0]["result"] == "no answer in 0.2s"


def test_a_single_failed_try_is_still_reported(queue) -> None:
    """No Gemini key: Qwen alone, once. One try is not a retry, but no answer
    is exactly what the admin needs to hear about."""
    with pytest.raises(RuntimeError):
        with reports.watching("Classification", EMAIL, "The email could not be sorted."):
            with_fallback(broken, answer, enabled=lambda: False)("text")

    row = only(queue)
    assert row["title"] == "Classification: no AI answer after 1 try"
    assert row["context"]["tries"] == 1


# --- each step the pipeline watches -------------------------------------------

def test_an_extraction_with_no_answer_says_what_happened_to_the_email(queue, monkeypatch) -> None:
    import backend.app as app
    monkeypatch.setattr(app, "extractor", AiExtractor(with_fallback(broken, broken), tries=2, wait=0))

    document = asyncio.run(app.extract_live(EMAIL, "SI", [("Shipper", "ACME")], None, "ok"))

    assert not any(field["present"] for field in document["fields"].values())
    row = only(queue)
    assert row["title"] == "Extraction (SI): no AI answer after 4 tries"
    assert row["detail"].startswith("Every field was treated as missing, so the email went to a person.")
    assert row["context"]["tries"] == 4


def test_a_classification_that_fails_is_reported_against_its_email(queue) -> None:
    from backend.classify import ClassificationFailed, EmailInput, classify_email
    email = EmailInput(email_id=EMAIL, from_email="ops@carrier.test", subject="Draft BL",
                       body="Please check the draft BL.", attachments=[])

    with pytest.raises(ClassificationFailed):
        asyncio.run(classify_email(email, model=with_fallback(broken, broken)))

    row = only(queue)
    assert row["email_ref"] == EMAIL
    assert row["title"] == "Classification: no AI answer after 2 tries"
    assert row["detail"].startswith("The email could not be sorted, so it was not checked.")


def test_a_reply_draft_with_no_model_is_reported(queue, monkeypatch) -> None:
    import backend.reply as reply
    from backend.classify import EmailInput
    # No real model may be reached from a test, whatever the developer's .env holds.
    monkeypatch.delenv("QWEN_API_KEY", raising=False)
    monkeypatch.setattr(reply, "client", None)
    monkeypatch.setattr(reply, "GEMINI_API_KEY", None)
    email = EmailInput(email_id=EMAIL, from_email="ops@carrier.test", subject="Invoice",
                       body="Why was I charged detention?", attachments=[])

    assert reply.generate_rag_reply(email, "INVOICE_QUERY") is None
    assert only(queue)["title"] == "Reply draft: no AI answer after 1 try"


def test_two_steps_at_once_keep_their_own_tries(queue) -> None:
    """SI and BL are read at the same time, and so are several emails. One
    struggling must not be booked against the other."""
    async def step(email_id: str, first) -> None:
        with reports.watching("Extraction (SI)", email_id, "not read"):
            await asyncio.to_thread(with_fallback(first, answer), "text")

    async def both() -> None:
        await asyncio.gather(step("email_a", broken), step("email_b", answer))

    asyncio.run(both())

    row = only(queue)
    assert row["email_ref"] == "email_a" and row["context"]["tries"] == 2


# --- the write ----------------------------------------------------------------

def test_the_report_goes_to_the_reports_table_with_the_service_key(queue) -> None:
    backup_step()
    reports.settle()

    request, row = queue[0]
    assert str(request.url) == f"{SUPABASE_URL}/rest/v1/reports"
    assert request.headers["apikey"] == SERVICE_KEY
    assert request.headers["authorization"] == f"Bearer {SERVICE_KEY}"
    assert "user_id" not in row  # automatic: no person filed it


def test_without_the_service_key_the_report_only_goes_to_the_log(queue, monkeypatch, caplog) -> None:
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY")
    caplog.set_level(logging.WARNING, logger="backend.reports")

    backup_step()

    assert filed(queue) == []
    assert "technical report: Classification: answered on try 2, by Gemini" in caplog.text


def test_a_database_that_refuses_never_reaches_the_check(monkeypatch, caplog) -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("database paused")

    use_database(monkeypatch, refuse)
    caplog.set_level(logging.WARNING, logger="backend.reports")

    with reports.watching("Classification", EMAIL, "not sorted"):
        result = with_fallback(broken, answer)("text")
    reports.settle()

    assert result["shipper"]["raw"] == "ACME"
    assert "technical report not saved" in caplog.text


def test_a_slow_database_does_not_hold_up_the_check(monkeypatch) -> None:
    def slow(request: httpx.Request) -> httpx.Response:
        time.sleep(1.0)
        return httpx.Response(201)

    use_database(monkeypatch, slow)

    started = time.perf_counter()
    backup_step()
    elapsed = time.perf_counter() - started
    reports.settle()

    assert elapsed < 0.5


# --- the admin queue ----------------------------------------------------------

def test_the_admin_queue_loads_each_reports_tries() -> None:
    select = re.search(r'\.select\("([^"]+)"\)', STORE[STORE.index("async function listReports"):])
    assert select and "context" in select.group(1).split(",")


def test_automatic_reports_are_listed_most_tries_first() -> None:
    screen = ADMIN[ADMIN.index("function screenList"):ADMIN.index("async function render")]
    assert "state.filter === KIND_TECHNICAL" in screen
    assert "tries(b) - tries(a)" in screen


def test_a_reports_tries_are_read_as_a_number_never_as_markup() -> None:
    """context comes from the database and is shown in the page: only a number
    may reach it, so a crafted row cannot inject markup through the count."""
    assert "Number(r.context && r.context.tries) || 0" in ADMIN
