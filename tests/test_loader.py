"""loader.Inbox, both ways it can be pointed.

The HTTP half runs against a real stdlib server on a spare port rather than a
mock, because what we actually need to know is that urllib talks to the
organisers' server correctly - and `submit()` only ever runs once, at the
deadline, when there is no time to debug it.
"""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from loader import Inbox

EMAIL = {
    "email_id": "email_001",
    "subject": "Please check the draft BL against the SI",
    "from": "ops@example.com",
    "body": "Attached are the SI and draft BL",
    "attachments": ["attachments/email_001_SI.txt", "attachments/email_001_BL.txt"],
}
SECOND_EMAIL = {**EMAIL, "email_id": "email_002", "attachments": []}
SI_TEXT = "SHIPPING INSTRUCTION\nShipper: APRIL FAR EAST (M) SDN BHD\n"
SAMPLE_SUBMISSION = {"email_001": {"category": "BL_COMPARISON", "status": "OK",
                                   "review_reason": None, "defect_fields": [],
                                   "has_defect": False}}
SCOREBOARD = {"final_score": 0.87, "stage1_macro_f1": 0.91}


@pytest.fixture
def bundle(tmp_path: Path) -> Path:
    """A miniature copy of the static bundle's layout."""
    inbox, attachments = tmp_path / "inbox", tmp_path / "attachments"
    inbox.mkdir()
    attachments.mkdir()
    for email in (EMAIL, SECOND_EMAIL):
        (inbox / f"{email['email_id']}.json").write_text(json.dumps(email), encoding="utf-8")
    (attachments / "email_001_SI.txt").write_text(SI_TEXT, encoding="utf-8")
    (tmp_path / "sample_submission.json").write_text(json.dumps(SAMPLE_SUBMISSION), encoding="utf-8")

    return tmp_path


# --- local bundle -------------------------------------------------------

def test_reads_every_email_in_the_folder(bundle: Path) -> None:
    assert [e["email_id"] for e in Inbox(str(bundle)).emails()] == ["email_001", "email_002"]


def test_iterating_the_inbox_is_the_same_as_calling_emails(bundle: Path) -> None:
    box = Inbox(str(bundle))

    assert list(box) == box.emails()


def test_fetches_one_email_by_id(bundle: Path) -> None:
    assert Inbox(str(bundle)).get("email_001")["subject"] == EMAIL["subject"]


def test_reads_an_attachment_as_text(bundle: Path) -> None:
    text = Inbox(str(bundle)).read_text("attachments/email_001_SI.txt")

    assert text.startswith("SHIPPING INSTRUCTION")


def test_unreadable_bytes_do_not_raise(bundle: Path) -> None:
    """A corrupt attachment is a NEEDS_REVIEW case downstream, not a crash
    here - read_text replaces what it cannot decode."""
    (bundle / "attachments" / "broken.txt").write_bytes(b"\xff\xfe\x00bad")

    assert Inbox(str(bundle)).read_text("attachments/broken.txt")


def test_sample_submission_comes_from_the_bundle(bundle: Path) -> None:
    assert Inbox(str(bundle)).sample_submission() == SAMPLE_SUBMISSION


def test_submitting_without_a_server_says_so(bundle: Path) -> None:
    """Silently doing nothing here would lose the submission."""
    with pytest.raises(RuntimeError, match="HTTP source"):
        Inbox(str(bundle)).submit(SAMPLE_SUBMISSION)


def test_a_trailing_slash_is_not_a_different_inbox(bundle: Path) -> None:
    assert Inbox(str(bundle) + "/").emails() == Inbox(str(bundle)).emails()


# --- the organisers' HTTP server ---------------------------------------

class StubInboxHandler(BaseHTTPRequestHandler):
    """The four endpoints the organiser server exposes, and nothing else."""

    posted: dict | None = None

    def _send(self, payload: bytes, content_type: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:  # noqa: N802 - name fixed by BaseHTTPRequestHandler
        routes = {
            "/emails": [EMAIL, SECOND_EMAIL],
            "/emails/email_001": EMAIL,
            "/sample_submission": SAMPLE_SUBMISSION,
        }
        if self.path in routes:
            return self._send(json.dumps(routes[self.path]).encode(), "application/json")
        if self.path == "/attachments/email_001_SI.txt":
            return self._send(SI_TEXT.encode(), "text/plain")

        self.send_error(404)

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/submit":
            return self.send_error(404)

        body = self.rfile.read(int(self.headers["Content-Length"]))
        StubInboxHandler.posted = json.loads(body)
        self._send(json.dumps(SCOREBOARD).encode(), "application/json")

    def log_message(self, *_args: object) -> None:
        """Quiet - the test output is the report."""


@pytest.fixture
def server() -> str:
    StubInboxHandler.posted = None
    httpd = HTTPServer(("127.0.0.1", 0), StubInboxHandler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{httpd.server_port}"
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_the_same_api_works_over_http(server: str) -> None:
    box = Inbox(server)

    assert [e["email_id"] for e in box.emails()] == ["email_001", "email_002"]
    assert box.get("email_001")["subject"] == EMAIL["subject"]
    assert box.read_text("attachments/email_001_SI.txt").startswith("SHIPPING INSTRUCTION")
    assert box.sample_submission() == SAMPLE_SUBMISSION


def test_submit_posts_the_submission_and_returns_the_scoreboard(server: str) -> None:
    scoreboard = Inbox(server).submit(SAMPLE_SUBMISSION)

    assert scoreboard == SCOREBOARD
    assert StubInboxHandler.posted == SAMPLE_SUBMISSION


def test_submit_sends_json(server: str) -> None:
    """The server rejects a body it cannot parse, and we get one attempt."""
    Inbox(server).submit(SAMPLE_SUBMISSION)

    assert isinstance(StubInboxHandler.posted, dict)


# --- against the real dataset ------------------------------------------

def test_the_real_bundle_holds_every_email(data_dir: Path) -> None:
    emails = Inbox(str(data_dir)).emails()

    assert len(emails) == 520
    assert all(e["email_id"].startswith("email_") for e in emails)
