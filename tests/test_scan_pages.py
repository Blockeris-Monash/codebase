"""The scanned pages sit beside what the model read from them (#147 A5).

"What the scan says" showed the model's reading and marked doubtful values "not verified",
with nothing to check them against. Each scanned attachment now has a small image of its
page, shown under the reading and loaded only when that email is opened.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

FRONTEND = Path(__file__).resolve().parents[1] / "frontend"
INDEX = (FRONTEND / "index.html").read_text(encoding="utf-8")
SCRIPT = INDEX[INDEX.index("<script>\n"):]
SCANS_JS = (FRONTEND / "scans.js").read_text(encoding="utf-8")
SCANS = json.loads(SCANS_JS[SCANS_JS.index("{"):SCANS_JS.rindex("}") + 1])
ALL_PAGES_BUDGET = 1024 * 1024


def readings() -> list[dict]:
    return [reading for roles in SCANS.values() for reading in roles.values()]


def test_every_scanned_reading_has_its_page() -> None:
    assert readings()
    for reading in readings():
        assert (FRONTEND / reading["page"]).is_file(), reading["page"]


def test_the_pages_together_stay_small() -> None:
    assert sum((FRONTEND / r["page"]).stat().st_size for r in readings()) < ALL_PAGES_BUDGET


def pages_html(scan: dict) -> str:
    start = SCRIPT.index("const SCAN_PAGES = ")
    end = SCRIPT.index("\n}\n", SCRIPT.index("function scanPagesHTML(")) + 3
    return subprocess.run(["node"], input="\n".join([
        "const T = s=>s, t = s=>s;",
        "const esc = s=>String(s??'').replace(/[&<>\"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;'}[c]));",
        SCRIPT[start:end],
        f"console.log(scanPagesHTML({json.dumps(scan)}));",
    ]), capture_output=True, text=True, check=True).stdout


def test_the_panel_shows_both_pages_lazily() -> None:
    html = pages_html(SCANS["email_512"])

    assert html.count("<img") == 2
    assert html.count('loading="lazy"') == 2
    assert 'href="scans/email_512_SI.webp"' in html


def test_a_reading_without_a_page_shows_no_image() -> None:
    assert pages_html({"SI": {"fields": {}}}) == "\n"


def test_the_images_are_not_precached_for_everyone() -> None:
    worker = (FRONTEND / "sw.js").read_text(encoding="utf-8")

    assert "scans/" not in re.search(r"const SHELL = \[.*?\];", worker).group(0)
