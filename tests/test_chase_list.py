"""D2: the draft BLs a sender was asked for and has not sent yet (#147 D2).

One item per (sender domain, shipment reference), oldest first; a later email from the
same domain with the same reference and a readable BL closes it, and the sender alone
never does. The page's own chaseList runs here in node, on the demo data and on made-up
live mail.
"""
from __future__ import annotations

import json

from tests.js_runner import FRONTEND, page_function, run_node

PAGE = (FRONTEND / "index.html").read_text(encoding="utf-8")
HELPERS = PAGE[PAGE.index("const DAY_MS = "):PAGE.index("function chaseList(")]
CHASE = HELPERS + page_function("chaseList")
DEMO = json.dumps(str(FRONTEND / "results.js"))


def test_the_demo_requests_group_by_sender_and_reference() -> None:
    result = run_node(f"""
        const {{readFileSync}} = await import("node:fs");
        const RESULTS = (0, eval)(readFileSync({DEMO}, "utf8").replace("const RESULTS =", "(") .replace(/;\\s*$/, ")"));
        {CHASE}
        const items = chaseList(RESULTS, Date.now());
        const requests = items.flatMap(i => i.requests);
        console.log(JSON.stringify({{requests: requests.length, withRef: requests.filter(e => e.ref).length,
                                     items: items.length, closed: items.filter(i => i.closed_by).length,
                                     unknownAge: items.every(i => i.age_days === null)}}));
    """)

    assert result == {"requests": 91, "withRef": 80, "items": 85, "closed": 0, "unknownAge": True}


LIVE = """
const request = (id, from, ref, at) => ({id, from, ref, awaiting: true, received_at: at});
const answer = (id, from, ref, at, status) => ({id, from, ref, received_at: at, docs: {BL: {parse_status: status}}});
const now = Date.parse("Fri, 25 Sep 2026 12:00:00 +0000");
"""


def chase(emails: str) -> list[dict]:
    return run_node(LIVE + CHASE + f"""
        const items = chaseList({emails}, now);
        console.log(JSON.stringify(items.map(i => ({{sender: i.sender, ref: i.ref, age: i.age_days,
                                                     closed_by: i.closed_by, n: i.requests.length}}))));
    """)


def test_a_bl_that_arrives_later_closes_its_item() -> None:
    items = chase("""[request("g1", "Ann <ann@ship.example>", "5ALT-01226", "Tue, 22 Sep 2026 09:00:00 +0000"),
                      answer("g2", "bob@ship.example", "5ALT-01226", "Wed, 23 Sep 2026 09:00:00 +0000", "ok")]""")

    assert items == [{"sender": "ship.example", "ref": "5ALT-01226", "age": 3, "closed_by": "g2", "n": 1}]


def test_a_bl_without_the_reference_or_unreadable_closes_nothing() -> None:
    items = chase("""[request("g1", "ann@ship.example", "5ALT-01226", "Tue, 22 Sep 2026 09:00:00 +0000"),
                      answer("g2", "ann@ship.example", "OTHER-0001", "Wed, 23 Sep 2026 09:00:00 +0000", "ok"),
                      answer("g3", "ann@ship.example", "5ALT-01226", "Wed, 23 Sep 2026 10:00:00 +0000", "unreadable"),
                      answer("g4", "ann@other.example", "5ALT-01226", "Wed, 23 Sep 2026 11:00:00 +0000", "ok")]""")

    assert [i["closed_by"] for i in items] == [None]


def test_the_same_reference_from_two_senders_is_two_items_oldest_first() -> None:
    items = chase("""[request("g1", "ann@new.example", "5ALT-01226", "Thu, 24 Sep 2026 09:00:00 +0000"),
                      request("g2", "bob@old.example", "5ALT-01226", "Mon, 21 Sep 2026 09:00:00 +0000"),
                      request("g3", "bob@old.example", "5ALT-01226", "Tue, 22 Sep 2026 09:00:00 +0000")]""")

    assert [(i["sender"], i["age"], i["n"]) for i in items] == [("old.example", 4, 2), ("new.example", 1, 1)]


ACTIONS = """
const S = {marks: {}, sent: {}, draft: null, drafting: null, sending: false, copied: null, copyFailed: null,
           refining: false, refineErr: null, sendErr: null, draftErr: null};
const t = s => s, esc = s => String(s), isLive = () => false, gmailLink = () => "#";
const REPLY_ASKS = {}, NEXT_STEP = {}, ICON = new Proxy({}, {get: () => ""});
""" + page_function("actionsHTML")

REQUEST = '{id: "email_011", from: "ann@ship.example", subject: "Draft BL", awaiting: true, status: "NEEDS_REVIEW", review_reason: "missing_attachment", rows: []}'


def test_a_reminder_opens_the_reply_box_on_the_request() -> None:
    """The request email had no actions at all, so Draft a reminder opened it with no reply box."""
    html = run_node(ACTIONS + f"""
        S.draft = {{id: "email_011", to: "ann@ship.example", subject: "Draft BL", body: "Dear team", reminder: true}};
        console.log(JSON.stringify(actionsHTML({REQUEST})));
    """)

    assert 'class="reply"' in html and "Remind the sender" in html and "Dear team" in html


def test_a_request_with_no_reminder_open_still_shows_no_actions() -> None:
    assert run_node(ACTIONS + f"console.log(JSON.stringify(actionsHTML({REQUEST})));") == ""
