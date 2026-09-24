"""Drafting a reply for a GENERAL or INVOICE_QUERY email (#93) must not freeze the server,
and a failed draft must never become the reply (#96).

generate_rag_reply() waits on the AI for up to 120 s. It was called straight inside the
async /process-email, which stops every other request on the event loop: mailbox polling,
Check again with AI and /health all waited. It now runs in a worker thread.

On failure it returned "An error occurred while generating the reply...", which the page
shows as the reply draft, and from My mailbox Send reply would email that sentence to the
customer. It now returns None, and the page offers no reply for that email."""
from __future__ import annotations

import asyncio
import time

import httpx

from backend import app as app_module
from backend import reply
from backend.classify import ClassificationResult

DRAFT_SECONDS = 1.5
GENERAL = {"email_id": "gmail_18c2f4e9a1b3d5f8", "from": "friend@example.com",
           "subject": "Dinner on Saturday?", "body": "Are you free after the finals?", "attachments": []}


def test_a_slow_reply_draft_does_not_hold_up_other_requests(monkeypatch) -> None:
    async def classify(email):
        return ClassificationResult(email_id=email.email_id, category="GENERAL", decided_by="llm",
                                    confidence=1.0, evidence="test")

    def slow_draft(email, category):
        time.sleep(DRAFT_SECONDS)   # a blocking AI call, as the real one is
        return "Hi, thanks for your email."

    monkeypatch.setattr(app_module, "classify", classify)
    monkeypatch.setattr(reply, "generate_rag_reply", slow_draft)

    async def run() -> tuple[float, dict]:
        transport = httpx.ASGITransport(app=app_module.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            checking = asyncio.create_task(client.post("/process-email", json=GENERAL))
            started = time.perf_counter()
            await asyncio.sleep(0.2)             # the draft is now being written
            health = await client.get("/health")
            waited = time.perf_counter() - started - 0.2   # time lost behind the draft
            assert health.status_code == 200
            return waited, (await checking).json()

    waited, checked = asyncio.run(run())

    assert waited < 0.5, f"/health waited {waited:.2f} s behind the reply draft"
    assert checked["draft_reply"] == "Hi, thanks for your email."


def test_a_failed_draft_is_empty_not_an_error_sentence(monkeypatch) -> None:
    def down(prompt, system_instruction):
        raise RuntimeError("gateway 502")

    monkeypatch.setattr(reply, "retrieve_policies", lambda query, top_k=3: [])
    monkeypatch.setattr(reply, "qwen_generate", down)
    monkeypatch.setattr(reply, "GEMINI_API_KEY", None)
    email = app_module.EmailInput(**GENERAL)

    assert reply.generate_rag_reply(email, "GENERAL") is None


def test_the_scorer_line_keeps_exactly_its_five_keys() -> None:
    """draft_reply sits beside SubmissionEntry, not in it: the organisers' line is unchanged."""
    assert set(app_module.SubmissionEntryOut.model_fields) == {
        "category", "status", "review_reason", "has_defect", "defect_fields"}
    assert "draft_reply" in app_module.ProcessedEmail.model_fields
