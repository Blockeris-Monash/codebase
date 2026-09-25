"""The review flow: open on the work, act first, keep going, and see how much is left.

Mentor feedback was that the screen felt like a list to browse, not a queue to work through. So the
page opens on Action required with the worst email first, the actions sit under the banner, Done or
Send moves on to the next email (with an Undo bar), and a progress line counts what is left.

Most checks read the source, as the other UI tests do. The ordering is run for real in node on the
saved results, using the page's own functions.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

FRONTEND = Path(__file__).resolve().parents[1] / "frontend"
INDEX = (FRONTEND / "index.html").read_text(encoding="utf-8")
SCRIPT = INDEX[INDEX.index("<script>\n"):]


def block(start: str, end: str = "\n};\n") -> str:
    at = SCRIPT.index(start)
    return SCRIPT[at:SCRIPT.index(end, at) + len(end)]


def branch(action: str) -> str:
    lines = [line for line in SCRIPT.splitlines() if f'a==="{action}"' in line]
    assert len(lines) == 1, f"expected one branch for {action!r}, found {len(lines)}"
    return lines[0]


def folder_order(folder: str, marks: dict[str, str] | None = None, sort: str = "worst") -> list[str]:
    """Run the page's items() on results.js for one folder, and return the ids in order."""
    js = "\n".join([
        (FRONTEND / "results.js").read_text(encoding="utf-8"),
        "const T = s=>s;",
        f"const S = {{q:'', f:{json.dumps(folder)}, sort:{json.dumps(sort)}, sel:null, mailbox:'demo', marks:{json.dumps(marks or {})}}};",
        block("const FOLDERS = [", "\n];\n"),
        re.search(r"const folder = .*\n", SCRIPT).group(0),
        re.search(r"const issues = .*\n", SCRIPT).group(0),
        re.search(r"const RANKED = .*\n", SCRIPT).group(0),
        re.search(r"const mailList = .*\n", SCRIPT).group(0),
        block("const items = ()=>{"),
        "console.log(JSON.stringify(items().map(e=>[e.id, issues(e)])));",
    ])
    out = subprocess.run(["node"], input=js, capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def test_the_page_opens_on_action_required() -> None:
    state = re.search(r"const S = \{.*\};", SCRIPT).group(0)
    assert 'f:"MISMATCH"' in state


def test_the_work_folders_put_the_worst_email_first() -> None:
    for folder in ("MISMATCH", "NEEDS_REVIEW"):
        counts = [n for _, n in folder_order(folder)]
        assert counts == sorted(counts, reverse=True), folder
        assert counts[0] > counts[-1], f"{folder} has nothing to sort"


def test_ties_and_other_folders_keep_the_saved_order() -> None:
    ids = [i for i, _ in folder_order("OTHER")]
    results = (FRONTEND / "results.js").read_text(encoding="utf-8")
    saved = re.findall(r'\{"id": "(email_\d+)"', results)
    assert ids == [i for i in saved if i in ids]
    twos = [i for i, n in folder_order("MISMATCH") if n == 2]
    assert twos == [i for i in saved if i in twos]


def test_newest_first_keeps_the_inbox_order() -> None:
    """The demo data has no dates, so newest means the inbox order (highest email number first)."""
    results = (FRONTEND / "results.js").read_text(encoding="utf-8")
    saved = re.findall(r'\{"id": "(email_\d+)"', results)
    ids = [i for i, _ in folder_order("MISMATCH", sort="new")]
    assert ids == [i for i in saved if i in ids]
    assert ids != [i for i, _ in folder_order("MISMATCH")], "the two orders should differ"


def test_fewest_issues_puts_the_one_field_emails_first() -> None:
    counts = [n for _, n in folder_order("MISMATCH", sort="least")]
    assert counts == sorted(counts)


def test_oldest_is_the_inbox_order_reversed() -> None:
    newest = [i for i, _ in folder_order("MISMATCH", sort="new")]
    assert [i for i, _ in folder_order("MISMATCH", sort="old")] == newest[::-1]


def test_sort_by_is_a_dropdown_with_most_issues_first() -> None:
    state = re.search(r"const S = \{.*\};", SCRIPT).group(0)
    assert 'sort:"worst"' in state
    assert 'pick("sortsel"' in SCRIPT and "S.sort=ev.target.value" in SCRIPT
    for label in ("Sort by", "Most issues", "Fewest issues", "Most recent", "Oldest"):
        assert f'T("{label}")' in SCRIPT or f't("{label}")' in SCRIPT, label


def test_the_actions_come_before_the_fields_table() -> None:
    detail = block("function detail(e){", "\n}\n")
    assert "h += banner + actionsHTML(e) + tbl;" in detail
    assert "table(view.rows)" not in detail.split("h += banner")[1], "the table is added somewhere else too"


def test_done_and_send_move_on_to_the_next_email() -> None:
    assert "advance(id)" in branch("mark")
    assert "advance(id)" in branch("send")
    advance = block("function advance(", "\n}\n")
    assert "S.toast" in advance, "the Undo bar must appear, the old Undo box leaves with the email"


def test_the_undo_bar_brings_the_email_back() -> None:
    undo = branch("undo")
    assert "S.toast" in undo and "S.sel=id" in undo


def test_an_empty_work_folder_says_all_done() -> None:
    assert 't("All done in this folder")' in SCRIPT


def test_the_progress_line_counts_what_is_left() -> None:
    assert 't("{done} of {total} done"' in SCRIPT
    todo = re.search(r"const todo = .*\n", SCRIPT).group(0)
    assert "MISMATCH" in todo and "NEEDS_REVIEW" in todo and "awaiting" in todo
