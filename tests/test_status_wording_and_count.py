"""The mentor's two asks for the review list: plainer status words, and a count of the fields to fix.

"Verified" replaces "Match", "Action required" replaces "Mismatch" and "Done" replaces "Checked",
in all three languages. Each
email in the list shows how many fields differ or are blank, so the worst ones are opened first.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

FRONTEND = Path(__file__).resolve().parents[1] / "frontend"
INDEX = (FRONTEND / "index.html").read_text(encoding="utf-8")
SCRIPT = INDEX[INDEX.index("<script>\n"):]


def test_the_page_says_verified_and_action_required() -> None:
    assert 'T("Verified")' in SCRIPT and 'T("Action required")' in SCRIPT
    assert 'T("Match")' not in SCRIPT and 'T("Mismatch")' not in SCRIPT
    assert '"Match")' not in SCRIPT and '"Mismatch")' not in SCRIPT, "a tile still uses the old word"


def test_the_reviewers_own_mark_says_done_not_checked() -> None:
    """Verified is the system's result; Done is what a person did. Checked sounded like Verified."""
    assert 'T("Done")' in SCRIPT and '"Mark as done"' in SCRIPT
    assert '"Checked"' not in SCRIPT and '"Mark as checked"' not in SCRIPT


def issue_counts() -> dict[str, int]:
    """Run the page's own count on the saved results, keyed by email id."""
    count_fn = re.search(r"const issues = e=>.*?;\n", SCRIPT).group(0)
    js = (
        (FRONTEND / "results.js").read_text(encoding="utf-8")
        + count_fn
        + "console.log(JSON.stringify(Object.fromEntries(RESULTS.map(e=>[e.id, issues(e)]))));"
    )
    out = subprocess.run(["node"], input=js, capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def test_a_mismatch_counts_each_differing_field() -> None:
    counts = issue_counts()
    assert counts["email_025"] == 2  # port of discharge and container count
    assert counts["email_004"] == 2  # consignee and notify party


def test_a_verified_or_non_comparison_email_counts_nothing() -> None:
    results = (FRONTEND / "results.js").read_text(encoding="utf-8")
    counts = issue_counts()
    ok_id = re.search(r'"id":\s*"(email_\d+)"[^{}]*?"status":\s*"OK"', results)
    assert ok_id, "no verified email found in results.js"
    assert counts[ok_id.group(1)] == 0
    assert all(n <= 7 for n in counts.values())


def test_the_count_sits_inside_the_list_badge() -> None:
    badge = re.search(r"const badge = e=>.*?;\n", SCRIPT).group(0)
    assert "issues(e)" in badge
