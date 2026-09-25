"""Signing out leaves nothing of the person on the browser (#147 B2).

Marks, replies, feedback and corrections stayed in localStorage after sign-out, and the
next person to sign in on the same browser had them merged into their own account. They
are now kept under the id of whoever made them. The page's own functions run here in
node against a fake localStorage.
"""
from __future__ import annotations

import json

import pytest

from tests.js_runner import FRONTEND, page_function, run_node

PAGE = (FRONTEND / "index.html").read_text(encoding="utf-8")
KEYS = PAGE[PAGE.index("const OWNER_KEY = "):PAGE.index("function forgetPersonalData(){")]


def after(owner: str, signed_in: str) -> dict:
    """What is left after an auth callback for `signed_in` ("" = signed out), on a browser
    whose saved data belongs to `owner`."""
    return run_node(f"""
        const store = new Map([["blockeris.owner", {json.dumps(owner)}],
                               ["blockeris.marks", '{{"email_001":"ok"}}'], ["blockeris.lang", "ms"]]);
        globalThis.localStorage = {{getItem: k => store.get(k) ?? null, setItem: (k, v) => store.set(k, String(v)),
                                    removeItem: k => store.delete(k)}};
        const S = {{marks: {{email_001: "ok"}}, sent: {{}}, corr: {{}}}};
        {KEYS}
        {page_function("forgetPersonalData")}
        {page_function("claimPersonalData")}
        claimPersonalData({json.dumps(signed_in)});
        console.log(JSON.stringify({{marks: store.has("blockeris.marks"), shown: Object.keys(S.marks).length,
                                     owner: store.get("blockeris.owner"), lang: store.get("blockeris.lang")}}));
    """)


@pytest.mark.parametrize("owner, signed_in", [("user-a", ""), ("user-a", "user-b")], ids=["sign-out", "someone-else"])
def test_another_persons_marks_are_cleared(owner: str, signed_in: str) -> None:
    left = after(owner, signed_in)

    assert (left["marks"], left["shown"]) == (False, 0)
    assert left["owner"] == signed_in
    assert left["lang"] == "ms", "a device preference is not personal data"


@pytest.mark.parametrize("owner, signed_in", [("user-a", "user-a"), ("", "user-a"), ("", "")],
                         ids=["same-person", "first-sign-in-adopts", "demo-visitor"])
def test_a_persons_own_marks_stay(owner: str, signed_in: str) -> None:
    left = after(owner, signed_in)

    assert (left["marks"], left["shown"]) == (True, 1)
