"""Phase B of the review flow: say what to do, show where the problem is, and a calmer screen.

- The main button names the next step for each case (the drafted reply for that case already exists).
- A differing or blank field tints its whole row, not one cell.
- Every email has a "Report a problem with this result" link into the support form.
- Language and colour mode live in one Settings menu instead of four top-bar buttons.
- The tiles are the work (Action required, Needs review, Verified, Done) plus Other mail, whose types
  are chips; the Show dropdown is gone, and search looks through all mail.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

FRONTEND = Path(__file__).resolve().parents[1] / "frontend"
INDEX = (FRONTEND / "index.html").read_text(encoding="utf-8")
SCRIPT = INDEX[INDEX.index("<script>\n"):]


def block(start: str, end: str = "\n}\n") -> str:
    at = SCRIPT.index(start)
    return SCRIPT[at:SCRIPT.index(end, at) + len(end)]


def branch(action: str) -> str:
    lines = [line for line in SCRIPT.splitlines() if f'a==="{action}"' in line]
    assert len(lines) == 1, f"expected one branch for {action!r}, found {len(lines)}"
    return lines[0]


def test_the_main_button_names_the_next_step_for_each_case() -> None:
    steps = block("const NEXT_STEP = {", "\n};\n")
    for reason in ("missing_value", "unreadable", "missing_attachment", "wrong_doc_type"):
        assert reason in steps
    assert 'T("Ask to fix the BL")' in steps
    assert "NEXT_STEP" in block("function actionsHTML(e){")


def test_a_problem_field_tints_its_whole_row() -> None:
    rows = block("function rowsHTML(rows){")
    assert '"bad"' in rows and '"gap"' in rows
    assert re.search(r"\.tbl tr\.bad td\{[^}]*--bad-soft", INDEX)
    assert re.search(r"\.tbl tr\.gap td\{[^}]*--rev-soft", INDEX)


def test_every_email_can_be_reported_from_the_detail() -> None:
    assert 'data-a="report"' in block("function detail(e){")
    report = branch("report")
    assert 'S.tab="support"' in report and 'kind:"problem"' in report


def test_language_and_colour_mode_share_one_settings_menu() -> None:
    assert 'data-a="settings"' in SCRIPT
    assert "themesw" not in INDEX, "the two theme buttons are still in the top bar"
    menu = block("function settingsHTML(")
    assert 'data-a="langpick"' in menu and 'data-a="theme"' in menu


def test_the_tiles_are_the_work_plus_other_mail() -> None:
    tiles = re.search(r'<div class="kpis">.*?</div>', SCRIPT).group(0)
    keys = re.findall(r'kp\("(\w+)"', tiles)
    assert keys == ["MISMATCH", "NEEDS_REVIEW", "OK", "CHECKED", "OTHER"]
    assert "foldersel" not in SCRIPT, "the Show dropdown is still there"


def other_counts() -> dict[str, int]:
    js = "\n".join([
        (FRONTEND / "results.js").read_text(encoding="utf-8"),
        "const T = s=>s; const S = {marks:{}};",
        block("const FOLDERS = [", "\n];\n"),
        "console.log(JSON.stringify(Object.fromEntries(FOLDERS.map(f=>[f.k, RESULTS.filter(f.f).length]))));",
    ])
    return json.loads(subprocess.run(["node"], input=js, capture_output=True, text=True, check=True).stdout)


def test_other_mail_holds_everything_that_is_not_a_check_result() -> None:
    n = other_counts()
    parts = ("AWAIT", "SI_REQUEST", "INVOICE_QUERY", "GENERAL", "SPAM")
    assert n["OTHER"] == sum(n[k] for k in parts)
    assert n["OTHER"] + n["MISMATCH"] + n["NEEDS_REVIEW"] + n["OK"] == 520


def test_other_mail_types_are_a_dropdown() -> None:
    assert 'pick("kindsel"' in SCRIPT and 't("Type")' in SCRIPT
    assert "kinds seg" not in SCRIPT, "the chip row is still there"


def test_search_looks_through_all_mail() -> None:
    items = block("const items = ()=>{", "\n};\n")
    assert "term ?" in items, "a search term should skip the folder filter"


def test_clicking_a_dropdown_does_not_redraw_the_page() -> None:
    """Every click redraws the page. A redraw on the click that opens a dropdown closes it again at once."""
    guard = [line for line in SCRIPT.splitlines() if 'a==="stay"' in line and "return" in line]
    assert len(guard) == 1
    assert 'a==="sortsel"' in guard[0] and 'a==="kindsel"' in guard[0]


def test_switching_mailbox_lands_on_a_folder_that_exists() -> None:
    """The mailbox switch reset the folder to "all", which Other mail replaced; folder() then found nothing.
    The switch is now the account menu: both of its actions must land on a real folder."""
    keys = re.findall(r'\{k:"(\w+)"', block("const FOLDERS = [", "\n];\n"))
    for act in ('else if(a==="demoacct"){', 'else if(a==="mymailbox"){'):
        target = re.search(r'S\.f="(\w+)"', block(act, "\n")).group(1)
        assert target in keys
