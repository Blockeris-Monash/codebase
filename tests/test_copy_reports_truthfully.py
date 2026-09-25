""""Copied" is shown only when the browser really copied (#147 B2).

writeText returns a promise, and both Copy buttons called it inside a synchronous try, so
a refused copy (no permission, not a secure context) still said "Copied".
"""
from __future__ import annotations

import pytest

from tests.js_runner import FRONTEND, page_function, run_node


@pytest.mark.parametrize("clipboard, copied", [
    ("{writeText: () => Promise.reject(new Error('denied'))}", False),
    ("{writeText: () => Promise.resolve()}", True),
    ("undefined", False),
], ids=["refused", "allowed", "no-clipboard"])
def test_the_outcome_is_the_browsers_answer(clipboard: str, copied: bool) -> None:
    result = run_node(f"""
        Object.defineProperty(globalThis, "navigator", {{value: {{clipboard: {clipboard}}}, configurable: true}});
        {page_function("copyText")}
        let told = null;
        await copyText("hello", ok => {{ told = ok; }});
        console.log(JSON.stringify(told));
    """)

    assert result is copied


def test_both_copy_buttons_wait_for_the_answer() -> None:
    page = (FRONTEND / "index.html").read_text(encoding="utf-8")
    handler = page[page.index('document.addEventListener("click", ev=>{'):]

    assert "navigator.clipboard.writeText" not in handler
    assert handler.count("copyText(") == 2
