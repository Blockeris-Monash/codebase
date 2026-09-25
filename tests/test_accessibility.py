"""Dialogs hold focus and text on the accent is readable (#147 B2).

Dialogs had no aria-modal and no focus trap, so Tab walked out into the page behind them;
and white on the orange accent was 3.4:1, under WCAG AA's 4.5:1 for text.
"""
from __future__ import annotations

import re

import pytest

from tests.js_runner import FRONTEND, page_function, run_node

PAGE = (FRONTEND / "index.html").read_text(encoding="utf-8")
STYLE = PAGE[PAGE.index("<style>"):PAGE.index("</style>")]
AA_TEXT = 4.5


def luminance(hex_colour: str) -> float:
    channels = [int(hex_colour[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast(a: str, b: str) -> float:
    high, low = sorted((luminance(a), luminance(b)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def theme_blocks() -> list[str]:
    """Every block that defines --accent-ink: light and dark, each plain and monotone, dark both ways in."""
    return [block for block in re.findall(r"\{([^{}]*--accent-ink:[^{}]*)\}", STYLE)]


def test_every_theme_defines_its_fill() -> None:
    assert len(theme_blocks()) == 6
    assert all("--accent-fill:" in block for block in theme_blocks())


@pytest.mark.parametrize("block", theme_blocks())
def test_text_on_the_accent_fill_meets_aa(block: str) -> None:
    fill = re.search(r"--accent-fill:(#[0-9a-f]{6})", block).group(1)
    ink = re.search(r"--accent-ink:(#[0-9a-f]{6})", block).group(1)

    assert contrast(fill, ink) >= AA_TEXT, (fill, ink)


def test_nothing_puts_accent_ink_straight_on_the_accent() -> None:
    rules = re.findall(r"\{([^{}]*)\}", STYLE)
    offenders = [r for r in rules if "background:var(--accent)" in r and "color:var(--accent-ink)" in r]

    assert offenders == []


def test_every_dialog_is_modal() -> None:
    dialogs = re.findall(r'<div[^>]*role="dialog"[^>]*>', PAGE)

    assert dialogs and all('aria-modal="true"' in d for d in dialogs)


FAKE_DIALOG = """
globalThis.CSS = {escape: s => s};
const button = name => ({name, focus() { document.activeElement = this; }});
const [first, middle, last, opener] = ["close", "tab", "send", "help"].map(button);
let open = true;
const dialog = {querySelectorAll: () => [first, middle, last], querySelector: () => first,
                contains: el => [first, middle, last].includes(el)};
globalThis.document = {activeElement: opener, body: {},
    querySelector: sel => sel.includes("dialog") ? (open ? dialog : null) : (sel.includes("help") ? opener : null)};
const key = (shiftKey) => ({key: "Tab", shiftKey, prevented: false, preventDefault() { this.prevented = true; }});
"""


def test_focus_goes_into_a_dialog_stays_there_and_comes_back() -> None:
    result = run_node(f"""
        {FAKE_DIALOG}
        const FOCUSABLE = "*";
        const dialogFocus = {{open: false, opener: null}};
        {page_function("refocus")}
        {page_function("focusDialog")}
        {page_function("trapTab")}
        focusDialog({{selector: "#help", start: null, end: null, top: 0}});
        const onOpen = document.activeElement.name;
        document.activeElement = last; trapTab(key(false)); const pastLast = document.activeElement.name;
        document.activeElement = first; trapTab(key(true)); const beforeFirst = document.activeElement.name;
        open = false; focusDialog(null);
        console.log(JSON.stringify([onOpen, pastLast, beforeFirst, document.activeElement.name]));
    """)

    assert result == ["close", "close", "send", "help"]
