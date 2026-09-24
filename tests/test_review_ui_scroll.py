"""Selecting an email must not send the inbox list back to the top.

`render()` in frontend/index.html rebuilds the whole page with one `innerHTML`
write, so every scroll box comes back at 0 and has to be restored from a
snapshot taken just before. The snapshot is skipped per container: `resetList`
for the inbox, `resetPane` for the open email.

The two are separate because the actions are. Changing folder, paging or
searching changes what the list holds, so the list belongs at the top.
Selecting an email changes only the pane; on a wide screen the list is a
separate box still on show, with the same rows in the same order, so it must
stay where the reader left it. One flag for both is the bug in
docs/issues/00-review-ui-scroll-jump.md: clicking a row scrolled the inbox to
the top, while the same move with the arrow keys did not.

These read the source rather than run it: the page has no build step and no
JavaScript test runner in this repo.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

UI = Path(__file__).resolve().parents[1] / "frontend" / "index.html"

# Actions that change only which email is shown. The list is untouched.
SELECTION_ONLY = ("open", "first", "back")
# Actions that change what the list holds. The list belongs back at the top.
LIST_CHANGING = ("folder", "newer", "older", "clearq")


def source() -> str:
    return UI.read_text(encoding="utf-8")


def branch(action: str) -> str:
    """The source line handling `data-a="<action>"`. Every branch is one line."""
    marker = f'a==="{action}"'
    lines = [line for line in source().splitlines() if marker in line]
    assert len(lines) == 1, f"expected one branch for {action!r}, found {len(lines)}"
    return lines[0]


def go_to() -> str:
    """The body of goTo(), which the arrow keys use to move between emails."""
    text = source()
    start = text.index("function goTo(")
    return text[start:text.index("\n}", start)]


@pytest.mark.parametrize("action", SELECTION_ONLY)
def test_selecting_an_email_does_not_reset_the_inbox_scroll(action: str) -> None:
    line = branch(action)

    assert "S.resetPane=true" in line, f"{action} changes the pane, so it must reset the pane"
    assert "S.resetList=true" not in line, (
        f"{action} does not change what the list holds, so resetting the list "
        f"scroll throws away the reader's place in the inbox")


def test_the_arrow_keys_reset_the_pane_only_too() -> None:
    body = go_to()

    assert "S.resetPane=true" in body
    assert "S.resetList=true" not in body


@pytest.mark.parametrize("action", LIST_CHANGING)
def test_changing_what_the_list_holds_sends_it_back_to_the_top(action: str) -> None:
    assert "S.resetList=true" in branch(action)


def test_a_click_leaves_the_selected_row_in_view_like_the_arrow_keys_do() -> None:
    """goTo sets keyNav so render() scrolls the selected row into view; a click must too.

    Without it, clicking a row near the bottom of a long list selected the email
    but left the row itself out of sight.
    """
    assert "S.keyNav=true" in go_to()
    assert "S.keyNav=true" in branch("open")


def test_the_snapshot_skips_each_container_on_its_own_flag() -> None:
    text = source()

    assert re.search(r"pane:\s*S\.resetPane\s*\?", text), "the pane snapshot must key off resetPane"
    assert re.search(r"list:\s*S\.resetList\s*\?", text), "the list snapshot must key off resetList"


def test_no_single_reset_flag_survives() -> None:
    """A revert to one `S.reset` for both containers brings the bug straight back."""
    assert not re.findall(r"S\.reset\b(?!List|Pane)", source())
