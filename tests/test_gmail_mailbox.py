"""Read the signed-in person's Gmail into /process-email, and reply from it (task 2, issue #75).

Offline: a fake Gmail answers in Google's own shapes, and the repository's rules
reader stands in for the model, so a result here is the pipeline's. Two people
share the fake server, to prove each one sees only their own mail.
"""
from __future__ import annotations

import asyncio
from collections import defaultdict
import base64
import email
import json
import time
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from backend import app as app_module
from backend import gmail
from backend.classify import ClassificationResult
from backend.extract.rules import fields_from_pairs

EDGE = Path(__file__).resolve().parent / "edge_cases" / "attachments"
SI = (EDGE / "email_901_SI.txt").read_bytes()
BL_WRONG_WEIGHT = (EDGE / "email_901_BL.txt").read_bytes().replace(b"21,577", b"21,977")


def b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def gmail_message(gmail_id: str, subject: str, body: str, files: list[tuple[str, bytes]] = (),
                  html: bool = False) -> dict:
    """A message as `users.messages.get?format=full` returns it: body inline,
    attachments by id, the way Gmail sends anything bigger than a few bytes."""
    text = {"mimeType": "text/html" if html else "text/plain", "filename": "", "body": {"data": b64(body.encode())}}
    parts = [text] + [{"mimeType": "text/plain", "filename": name,
                       "body": {"attachmentId": f"att{n}", "size": len(data)}} for n, (name, data) in enumerate(files)]
    return {"id": gmail_id, "threadId": "t" + gmail_id,
            "payload": {"mimeType": "multipart/mixed", "headers": [
                {"name": "From", "value": "Lee Guan <lee@shipper.example>"},
                {"name": "To", "value": "desk@ours.example"},
                {"name": "Subject", "value": subject},
                {"name": "Message-ID", "value": f"<{gmail_id}@mail.example>"},
                {"name": "Date", "value": "Thu, 24 Sep 2026 22:10:00 +1000"}],
                "parts": parts}}


class FakeGmail:
    """Two mailboxes behind one Gmail, told apart by the token, as Google does."""

    def __init__(self) -> None:
        self.people = {"token-a": "a@ours.example", "token-b": "b@ours.example"}
        self.files = {"18c2f4e9a1b3d5f7": [("instruction.txt", SI), ("draft for checking.txt", BL_WRONG_WEIGHT)]}
        self.boxes = {
            "token-a": {"18c2f4e9a1b3d5f7": gmail_message("18c2f4e9a1b3d5f7", "RE: 5ALT-01226 draft BL",
                                                          "Pls check the draft BL against the SI.",
                                                          self.files["18c2f4e9a1b3d5f7"]),
                        "18c2f4e9a1b3d5f8": gmail_message("18c2f4e9a1b3d5f8", "Lunch", "<p>Lunch at 1?</p>",
                                                          html=True)},
            "token-b": {"28c2f4e9a1b3d5f7": gmail_message("28c2f4e9a1b3d5f7", "Private", "Not for A.")},
        }
        self.sent: list[dict] = []
        self.expired = False

    def __call__(self, request: httpx.Request) -> httpx.Response:
        token = request.headers["Authorization"].removeprefix("Bearer ")
        if self.expired or token not in self.people:
            return httpx.Response(401, json={"error": {"message": "Invalid Credentials"}})
        box, path = self.boxes[token], request.url.path.removeprefix("/gmail/v1/users/me")
        if path == "/profile":
            return httpx.Response(200, json={"emailAddress": self.people[token]})
        if path == "/messages":
            return httpx.Response(200, json={"messages": [{"id": i} for i in box]})
        if path == "/messages/send":
            self.sent.append({"token": token, **json.loads(request.content)})
            return httpx.Response(200, json={"id": "sent1", "threadId": self.sent[-1].get("threadId")})
        parts = path.split("/")
        if len(parts) >= 3 and parts[2] in box:
            if len(parts) == 5:  # /messages/<id>/attachments/<att>
                return httpx.Response(200, json={"data": b64(self.files[parts[2]][int(parts[4][3:])][1])})
            return httpx.Response(200, json=box[parts[2]])
        return httpx.Response(404, json={"error": {"message": "Requested entity was not found."}})


class RulesReader:
    def extract_fields(self, email_id: str, pairs: list[tuple[str, str]]) -> dict:
        return fields_from_pairs(pairs)


@pytest.fixture
def google(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    fake = FakeGmail()
    classified: list[str] = []

    async def classify(email):
        classified.append(email.email_id)
        category = "BL_COMPARISON" if email.attachments else "GENERAL"
        return ClassificationResult(email_id=email.email_id, category=category, decided_by="llm",
                                    confidence=1.0, evidence="test")

    monkeypatch.setattr(gmail, "TRANSPORT", httpx.MockTransport(fake))
    monkeypatch.setattr(app_module, "classify", classify)
    monkeypatch.setattr(app_module, "extractor", RulesReader())
    monkeypatch.setattr(app_module, "MAILBOX_DIR", tmp_path)
    for store in ("MAILBOXES", "ORIGINALS", "WORKING", "FAILURES"):
        monkeypatch.setattr(app_module, store, {})
    monkeypatch.setattr(app_module, "CHECKS", defaultdict(lambda: asyncio.Semaphore(2)))
    fake.classified = classified
    with TestClient(app_module.app) as client:
        fake.client = client
        yield fake


def poll(client: TestClient, token: str, want: int) -> list[dict]:
    """Ask as the page does, every so often, until `want` emails are checked."""
    deadline = time.time() + 20
    while True:
        got = client.get("/mailbox", headers={"Authorization": f"Bearer {token}"})
        assert got.status_code == 200, got.text
        if len(got.json()) >= want or time.time() > deadline:
            return got.json()
        time.sleep(0.05)


# ---------------------------------------------------------------- reading

def test_a_gmail_message_gives_its_body_headers_and_attachments() -> None:
    raw = gmail_message("18c2f4e9a1b3d5f7", "RE: draft", "Please check.", [("si.pdf", b"x")])

    message = gmail.parse_message(raw)

    assert (message.sender, message.subject, message.body) == ("Lee Guan <lee@shipper.example>", "RE: draft", "Please check.")
    assert message.message_id == "<18c2f4e9a1b3d5f7@mail.example>" and message.thread_id == "t18c2f4e9a1b3d5f7"
    assert [(a.filename, a.attachment_id) for a in message.attachments] == [("si.pdf", "att0")]


def test_an_html_only_email_is_read_as_text() -> None:
    raw = gmail_message("1", "Hi", "<p>Dear team,<br>see &amp; check</p><style>p{}</style>", html=True)

    assert gmail.parse_message(raw).body == "Dear team,\nsee & check"


def test_attachments_are_named_by_the_documents_own_title_not_the_senders_name(tmp_path: Path) -> None:
    """The comparator trusts the title, so the pairing must too. The sender's file
    name never becomes a path, so '../' cannot write outside the folder."""
    files = [("draft.txt", BL_WRONG_WEIGHT), ("../../evil.txt", SI), ("photo.png", b"\x89PNG")]

    saved = [Path(p) for p in gmail.save_attachments("gmail_ab12cd34", files, tmp_path)]

    assert [p.name for p in saved] == ["gmail_ab12cd34_BL.txt", "gmail_ab12cd34_SI.txt", "gmail_ab12cd34_file3.png"]
    assert all(p.parent == tmp_path for p in saved)


def test_a_second_si_and_bl_become_a_second_shipment(tmp_path: Path) -> None:
    files = [("a.txt", SI), ("b.txt", BL_WRONG_WEIGHT), ("c.txt", SI), ("d.txt", BL_WRONG_WEIGHT)]

    names = [Path(p).name for p in gmail.save_attachments("gmail_ab12cd34", files, tmp_path)]

    assert names == ["gmail_ab12cd34_SI.txt", "gmail_ab12cd34_BL.txt", "gmail_ab12cd34_SI_2.txt", "gmail_ab12cd34_BL_2.txt"]


def test_the_mailbox_needs_a_google_token(google) -> None:
    assert google.client.get("/mailbox").status_code == 401
    assert google.client.get("/mailbox?user_id=anyone").status_code == 401


def test_a_new_email_is_checked_and_shows_its_discrepancy(google) -> None:
    emails = {e["id"]: e for e in poll(google.client, "token-a", 2)}

    checked = emails["gmail_18c2f4e9a1b3d5f7"]
    assert checked["status"] == "MISMATCH" and checked["defect_fields"] == ["gross_weight_kg"]
    assert set(checked["docs"]) == {"SI", "BL"} and checked["ref"] == "5ALT-01226"
    assert checked["from"] == "Lee Guan <lee@shipper.example>"
    other = emails["gmail_18c2f4e9a1b3d5f8"]
    assert other["category"] == "GENERAL" and "status" not in other  # Other mail, as a demo email would be


def test_fetching_again_does_not_duplicate_or_recheck(google) -> None:
    first = poll(google.client, "token-a", 2)

    again = google.client.get("/mailbox", headers={"Authorization": "Bearer token-a"})

    assert again.json() == first and len(first) == 2
    # the SI and BL email is sorted by rule (backend/app.py sort_email), so only the other asks the AI
    assert google.classified == ["gmail_18c2f4e9a1b3d5f8"]
    assert again.headers["X-Mailbox-Pending"] == "0"


def test_the_page_on_another_site_can_read_how_many_are_still_being_checked(google) -> None:
    got = google.client.get("/mailbox", headers={"Authorization": "Bearer token-a",
                                                 "Origin": "https://shiphappens-iota.vercel.app"})

    assert "x-mailbox-pending" in got.headers.get("access-control-expose-headers", "").lower()


def test_one_person_never_sees_another_persons_mail(google) -> None:
    poll(google.client, "token-a", 2)

    theirs = poll(google.client, "token-b", 1)

    assert [e["id"] for e in theirs] == ["gmail_28c2f4e9a1b3d5f7"]


def test_an_expired_token_asks_for_a_new_sign_in(google) -> None:
    google.expired = True

    got = google.client.get("/mailbox", headers={"Authorization": "Bearer token-a"})

    assert got.status_code == 401 and "Sign in" in got.json()["detail"]


# ---------------------------------------------------------------- replying

def sent_message(google) -> email.message.Message:
    raw = google.sent[-1]["raw"]
    return email.message_from_bytes(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)))


def test_a_reply_goes_out_from_their_gmail_in_the_same_thread(google) -> None:
    poll(google.client, "token-a", 2)

    got = google.client.post("/reply", headers={"Authorization": "Bearer token-a"},
                             json={"email_id": "gmail_18c2f4e9a1b3d5f7", "to": "Lee Guan <lee@shipper.example>",
                                   "subject": "RE: 5ALT-01226 draft BL", "body": "Gross weight differs."})

    assert got.status_code == 200 and got.json()["sent"] is True
    assert google.sent[-1]["threadId"] == "t18c2f4e9a1b3d5f7"
    msg = sent_message(google)
    assert msg["From"] == "a@ours.example" and msg["To"] == "Lee Guan <lee@shipper.example>"
    assert msg["In-Reply-To"] == msg["References"] == "<18c2f4e9a1b3d5f7@mail.example>"
    assert msg.get_payload().strip() == "Gross weight differs."


def test_a_reply_works_before_the_email_was_checked_here(google) -> None:
    """After a restart the server has seen nothing; the original is fetched again."""
    got = google.client.post("/reply", headers={"Authorization": "Bearer token-a"},
                             json={"email_id": "gmail_18c2f4e9a1b3d5f7", "to": "lee@shipper.example",
                                   "subject": "Re: x", "body": "ok"})

    assert got.status_code == 200 and sent_message(google)["Subject"] == "Re: x"


def test_a_demo_email_is_never_really_sent(google) -> None:
    """The demo emails carry real companies' addresses."""
    got = google.client.post("/reply", headers={"Authorization": "Bearer token-a"},
                             json={"email_id": "email_499", "to": "guancheng_lee@april.com.my",
                                   "subject": "Re: x", "body": "hi"})

    assert got.status_code == 404 and google.sent == []


def test_nobody_can_reply_to_an_email_in_someone_elses_mailbox(google) -> None:
    got = google.client.post("/reply", headers={"Authorization": "Bearer token-a"},
                             json={"email_id": "gmail_28c2f4e9a1b3d5f7", "to": "x@y.example",
                                   "subject": "Re: x", "body": "hi"})

    assert got.status_code == 404 and google.sent == []


@pytest.mark.parametrize("to", ["a@x.example, b@x.example", "a@x.example\r\nBcc: all@x.example", "not an address"])
def test_a_reply_goes_to_exactly_one_address(google, to: str) -> None:
    got = google.client.post("/reply", headers={"Authorization": "Bearer token-a"},
                             json={"email_id": "gmail_18c2f4e9a1b3d5f7", "to": to, "subject": "Re: x", "body": "hi"})

    assert got.status_code == 422 and google.sent == []


def test_a_subject_cannot_add_headers_of_its_own(google) -> None:
    got = google.client.post("/reply", headers={"Authorization": "Bearer token-a"},
                             json={"email_id": "gmail_18c2f4e9a1b3d5f7", "to": "lee@shipper.example",
                                   "subject": "Re: x\r\nBcc: all@x.example", "body": "hi"})

    assert got.status_code == 422 and google.sent == []


def test_a_reply_needs_a_google_token(google) -> None:
    got = google.client.post("/reply", json={"email_id": "gmail_18c2f4e9a1b3d5f7", "to": "a@b.example",
                                             "subject": "x", "body": "y"})

    assert got.status_code == 401 and google.sent == []


def test_a_live_email_gets_an_intent_and_keeps_its_subject_as_the_title_words(google) -> None:
    """Real subjects do not follow the dataset's shapes, so when the rules find no customer
    or port, the title is the label and the subject: "SI vs BL: RE: 5ALT-01226 draft BL"."""
    emails = {e["id"]: e for e in poll(google.client, "token-a", 2)}

    checked = emails["gmail_18c2f4e9a1b3d5f7"]
    assert checked["intent"] == "check_draft_bl"
    assert checked["about"] == ["RE: 5ALT-01226 draft BL"]


def test_a_live_email_no_rule_knows_has_no_intent(google) -> None:
    """The page then shows the subject, exactly as before."""
    emails = {e["id"]: e for e in poll(google.client, "token-a", 2)}

    assert "intent" not in emails["gmail_18c2f4e9a1b3d5f8"] and "about" not in emails["gmail_18c2f4e9a1b3d5f8"]


def test_an_si_and_bl_email_is_checked_while_the_ai_is_down(google, monkeypatch) -> None:
    """25 Sep: Qwen timed out and Gemini was out of quota, so this email became
    "(could not be checked)". With both documents attached it needs no AI at all."""
    async def ai_down(email):
        raise app_module.HTTPException(status_code=502, detail="The read operation timed out")
    monkeypatch.setattr(app_module, "classify", ai_down)

    emails = {e["id"]: e for e in poll(google.client, "token-a", 2)}

    checked = emails["gmail_18c2f4e9a1b3d5f7"]
    assert checked["status"] == "MISMATCH" and checked["defect_fields"] == ["gross_weight_kg"]
    assert checked["decided_by"] == "rule"
    assert emails["gmail_18c2f4e9a1b3d5f8"]["category"] == "GENERAL"  # filed by the keyword rule, not lost


def test_a_mailbox_email_is_read_by_rule_before_the_model(google, monkeypatch) -> None:
    """The mailbox asked process_email for live=True, which forces the model and skips the
    rules-first reader (#122) that uploads and the demo already use. A Gmail id is never in
    the saved results, so the normal path loses nothing and needs no AI for labelled files."""
    class ModelDown:
        def extract_fields(self, email_id, pairs):
            raise RuntimeError("QWEN_API_KEY is not set")
    async def ai_down(email):
        raise app_module.HTTPException(status_code=502, detail="The read operation timed out")
    monkeypatch.setattr(app_module, "extractor", ModelDown())
    monkeypatch.setattr(app_module, "classify", ai_down)

    emails = {e["id"]: e for e in poll(google.client, "token-a", 2)}

    checked = emails["gmail_18c2f4e9a1b3d5f7"]
    assert checked["status"] == "MISMATCH" and checked["defect_fields"] == ["gross_weight_kg"]
