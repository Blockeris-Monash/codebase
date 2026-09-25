"""A mailbox email the backend gave up on, and one that left the list, both open without crashing.

Two ways the detail pane froze in My mailbox (#147 A1):

- An email that failed its check twice was stored with no category, and the pane called
  `.toLowerCase()` on it. The row could never be opened, and every 10 s poll threw again.
- An email that dropped out of the next poll (newer mail, archived in Gmail, a restart) left
  `S.sel` pointing at nothing, and `detail(undefined)` threw.

The page's own functions are run in node, as tests/test_review_flow.py does.
"""
from __future__ import annotations

import asyncio
import json
import re
import subprocess
from pathlib import Path

from backend import app as app_module
from backend.contracts import CategoryType

FRONTEND = Path(__file__).resolve().parents[1] / "frontend"
INDEX = (FRONTEND / "index.html").read_text(encoding="utf-8")
SCRIPT = INDEX[INDEX.index("<script>\n"):]


def function(name: str) -> str:
    at = SCRIPT.index(f"function {name}(")
    return SCRIPT[at:SCRIPT.index("\n}\n", at) + 3]


def run_node(lines: list[str]) -> str:
    return subprocess.run(["node"], input="\n".join(lines), capture_output=True, text=True, check=True).stdout


class GmailDown:
    """Stands in for backend.gmail.Gmail when every fetch fails."""

    def __init__(self, token: str) -> None:
        self.token = token

    async def __aenter__(self) -> "GmailDown":
        raise ConnectionError("Gmail unreachable")

    async def __aexit__(self, *exc: object) -> None:
        return None


def give_up_on(monkeypatch, address: str, gmail_id: str) -> dict:
    monkeypatch.setattr(app_module, "MAILBOXES", {})
    monkeypatch.setattr(app_module, "FAILURES", {})
    monkeypatch.setattr(app_module.gmail, "Gmail", GmailDown)
    monkeypatch.setattr(app_module.reports, "file", lambda report: None)
    for _ in range(app_module.GIVE_UP_AFTER):
        asyncio.run(app_module.check_message("token", address, gmail_id))

    return app_module.MAILBOXES[address][gmail_id]


def test_an_email_given_up_on_still_has_a_category(monkeypatch) -> None:
    entry = give_up_on(monkeypatch, "failed@example.com", "abc123")

    assert entry["check_failed"] is True
    assert entry["category"] == CategoryType.General


def test_an_email_given_up_on_opens_without_touching_the_result_sections() -> None:
    entry = {"id": "gmail_abc123", "subject": "(could not be checked)", "check_failed": True}
    out = run_node([
        "const esc = s=>String(s??'');",
        "const t = s=>s;",
        "const ICON = {NEEDS_REVIEW: ''};",
        "const gmailLink = e=>'https://mail.google.com/#all/' + e.id;",
        # Every section of a normal pane throws, so reaching one fails the test.
        "const how = ()=>{ throw new Error('how() ran'); };",
        "const title = how, who = how, routeHTML = how;",
        function("failedHTML"),
        function("detail"),
        f"console.log(detail({json.dumps(entry)}));",
    ])

    assert "Could not be checked" in out
    assert "Open in Gmail" in out


def selected_after(sel: str, live_ids: list[str]) -> list[object]:
    return json.loads(run_node([
        "const RESULTS = [{id:'email_001'}];",
        f"const S = {{sel:{json.dumps(sel)}, mailbox:'live', liveEmails:{json.dumps([{'id': i} for i in live_ids])}, uploads:[]}};",
        re.search(r"const byId = .*\n", SCRIPT).group(0),
        re.search(r"const rawList = .*\n", SCRIPT).group(0),
        re.search(r"const mailList = .*\n", SCRIPT).group(0),
        re.search(r"const getEmail = .*\n", SCRIPT).group(0),
        re.search(r"const selectedEmail = .*\n", SCRIPT).group(0),
        "const e = selectedEmail();",
        "console.log(JSON.stringify([e && e.id, S.sel]));",
    ]))


def test_a_selection_that_left_the_list_is_dropped() -> None:
    assert selected_after("gmail_gone", ["gmail_other"]) == [None, None]


def test_a_selection_still_in_the_list_stays_open() -> None:
    assert selected_after("gmail_here", ["gmail_here"]) == ["gmail_here", "gmail_here"]


def test_the_pane_opens_the_selection_through_the_guard() -> None:
    assert "const open = selectedEmail();" in SCRIPT
    assert "detail(getEmail(S.sel))" not in SCRIPT
