"""My mailbox is polled only while it is on screen, one request at a time, and never after
sign-out (#147 B2).

setInterval polled every 10 s from sign-in on: on the landing page, on What's next and in
a hidden tab. A slow answer overlapped the next request, and one still in flight at
sign-out landed afterwards and filled the list again. The page's polling block runs here
in node against a stub screen and a network the test answers by hand.
"""
from __future__ import annotations

from tests.js_runner import FRONTEND, run_node

PAGE = (FRONTEND / "index.html").read_text(encoding="utf-8")
POLLER = PAGE[PAGE.index("const POLL_MS = "):PAGE.index("/* Mail from the person's own Gmail has a gmail_ id.")]

HARNESS = """
const S = {mailbox: "live", user: {id: "u"}, liveEmails: [], liveLoaded: false, pending: 0};
const screen = {home: false, hash: "#/inbox", visible: "visible"};
const isHome = () => screen.home;
globalThis.location = {get hash() { return screen.hash; }};
globalThis.document = {get visibilityState() { return screen.visible; }, addEventListener() {}};
globalThis.window = {Store: {googleToken: () => "token"}};
const API_BASE = "", T = s => s;
let renders = 0; const render = () => { renders++; };
const calls = [];
globalThis.fetch = (url, options) => new Promise((resolve, reject) => {
    const call = {answer: data => resolve({ok: true, status: 200, headers: {get: () => "0"},
                                           text: async () => JSON.stringify(data)})};
    options.signal.addEventListener("abort", () => reject(Object.assign(new Error("aborted"), {name: "AbortError"})));
    calls.push(call);
});
const settle = () => new Promise(r => setTimeout(r, 5));
"""


def run(steps: str) -> dict:
    return run_node(HARNESS + POLLER + steps + "\nstopPolling();")


def test_nothing_is_polled_on_the_landing_page_or_in_a_hidden_tab() -> None:
    result = run("""
        screen.home = true; syncPolling(); await settle();
        screen.home = false; screen.visible = "hidden"; syncPolling(); await settle();
        console.log(JSON.stringify({calls: calls.length}));
    """)

    assert result == {"calls": 0}


def test_one_request_at_a_time_however_often_the_page_redraws() -> None:
    result = run("""
        syncPolling(); await settle();
        syncPolling(); syncPolling(); await settle();
        console.log(JSON.stringify({calls: calls.length}));
    """)

    assert result == {"calls": 1}


def test_an_answer_that_lands_after_sign_out_is_dropped() -> None:
    result = run("""
        syncPolling(); await settle();
        S.user = null; stopPolling();
        calls[0].answer([{id: "gmail_1"}]); await settle();
        console.log(JSON.stringify({emails: S.liveEmails.length, calls: calls.length}));
    """)

    assert result == {"emails": 0, "calls": 1}


def test_an_answer_on_screen_is_shown() -> None:
    result = run("""
        syncPolling(); await settle();
        calls[0].answer([{id: "gmail_1"}]); await settle();
        console.log(JSON.stringify({emails: S.liveEmails.length, loaded: S.liveLoaded}));
    """)

    assert result == {"emails": 1, "loaded": True}


def test_the_same_answer_again_does_not_redraw_the_page() -> None:
    """A redraw rebuilds the reply box someone may be typing in; a quiet mailbox has no news."""
    result = run("""
        syncPolling(); await settle();
        calls[0].answer([{id: "gmail_1"}]); await settle();
        const first = renders;
        schedulePoll(0); await settle();
        calls[1].answer([{id: "gmail_1"}]); await settle();
        console.log(JSON.stringify({extra: renders - first}));
    """)

    assert result == {"extra": 0}
