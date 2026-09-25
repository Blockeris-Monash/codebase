"""Mirroring to the database notices when the database says no (#147 B2).

supabase-js resolves with `{data, error}` when a request is refused; it does not throw.
pushMark and pushReply ignored that error, and pull and isAdmin read a refusal as "no
rows", so a rejected write looked exactly like a saved one. store.js runs here in node
against a fake client that refuses every request.
"""
from __future__ import annotations

import json

import pytest

from tests.js_runner import FRONTEND, run_node

STORE = json.dumps(str(FRONTEND / "store.js"))

REFUSING_CLIENT = """
const refused = {data: null, error: {message: "new row violates row-level security policy"}};
const query = new Proxy({}, {get: (_, key) => key === "then"
    ? (resolve) => resolve(refused)
    : () => query});
globalThis.window = globalThis;
window.SUPABASE_URL = "https://example.supabase.co";
window.SUPABASE_ANON_KEY = "sb_publishable_test";
window.supabase = {createClient: () => ({
    from: () => query,
    auth: {getUser: async () => ({data: {user: {id: "user-1"}}})},
})};
globalThis.warned = [];
console.warn = (...args) => warned.push(String(args[0]));
"""


@pytest.mark.parametrize("call, refused_answer", [
    ('Store.pushMark("email_001", "ok")', False),
    ('Store.pushReply("email_001", {to: "a@b.c", subject: "s", body: "b"})', False),
    ('Store.pull({})', None),
    ('Store.isAdmin()', False),
    ('Store.listReports()', None),
    ('Store.pushReport({kind: "problem", msg: "x"})', False),
])
def test_a_refused_request_is_logged_and_reported_as_not_done(call: str, refused_answer: object) -> None:
    answer, warned = run_node(f"""
        {REFUSING_CLIENT}
        const {{readFileSync}} = await import("node:fs");
        (0, eval)(readFileSync({STORE}, "utf8"));
        const answer = await {call};
        console.log(JSON.stringify([answer, warned.length]));
    """)

    assert answer == refused_answer
    assert warned == 1, "the refusal was not logged"
