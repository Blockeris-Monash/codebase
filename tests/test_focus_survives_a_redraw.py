"""A redraw puts focus, the cursor and the selection back where they were (#147 B2).

The page rebuilds itself with one innerHTML write, so the focused element is destroyed:
a reply being typed lost its cursor to every poll, and keyboard users fell back to <body>
after every click. The page's own focusOf and refocus run here in node.
"""
from __future__ import annotations

import pytest

from tests.js_runner import page_function, run_node

FAKE_DOM = """
globalThis.CSS = {escape: s => String(s).replace(/"/g, '\\\\"')};
const made = {};
function element(tag, props) {
    const el = {tagName: tag.toUpperCase(), dataset: {}, id: "", scrollTop: 0, ...props,
                closest: () => true, focus() { document.activeElement = this; },
                setSelectionRange(a, b) { this.selectionStart = a; this.selectionEnd = b; }};
    return el;
}
globalThis.document = {body: {}, activeElement: null, querySelector: selector => made[selector] || null};
"""


@pytest.mark.parametrize("props, selector", [
    ('{id: "r-body", selectionStart: 5, selectionEnd: 9, scrollTop: 40}', "#app #r-body"),
    ('{dataset: {a: "open", id: "email_001"}}', '#app button[data-a="open"][data-id="email_001"]'),
    ('{dataset: {f: "instruction"}, selectionStart: 2, selectionEnd: 2}', '#app [data-f="instruction"]'),
], ids=["reply-box", "list-item", "refine-box"])
def test_the_rebuilt_element_gets_focus_cursor_and_scroll_back(props: str, selector: str) -> None:
    tag = "button" if "open" in props else "textarea"
    result = run_node(f"""
        {FAKE_DOM}
        {page_function("focusOf")}
        {page_function("refocus")}
        const before = element({tag!r}, {props});
        const saved = focusOf(before);
        const rebuilt = element({tag!r}, {{}});
        made[{selector!r}] = rebuilt;
        refocus(saved);
        console.log(JSON.stringify({{focused: document.activeElement === rebuilt, start: rebuilt.selectionStart ?? null,
                                     end: rebuilt.selectionEnd ?? null, top: rebuilt.scrollTop}}));
    """)

    assert result["focused"] is True
    before = run_node(f"const p = {props}; console.log(JSON.stringify([p.selectionStart ?? null, p.selectionEnd ?? null, p.scrollTop ?? 0]));")
    assert [result["start"], result["end"], result["top"]] == before


def test_nothing_is_chased_when_the_element_is_gone() -> None:
    result = run_node(f"""
        {FAKE_DOM}
        {page_function("focusOf")}
        {page_function("refocus")}
        refocus(focusOf(element("button", {{dataset: {{a: "open", id: "email_009"}}}})));
        console.log(JSON.stringify(document.activeElement));
    """)

    assert result is None
