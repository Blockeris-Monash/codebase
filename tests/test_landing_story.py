"""The landing page tells the story like a product page: problem, how we solve it, results, team.

Every number on it comes from the deck or is computed from the saved results, so the page and the
pitch cannot drift apart. The pipeline is interactive (four steps on one real email, email_302) and
switches steps without redrawing the page, so it never throws the reader back to the top.
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


def test_the_landing_page_has_every_section_in_story_order() -> None:
    home = block("function homePage(){")
    ids = re.findall(r'id="(\w+)"', home)
    # "Get started" sits right under the hero, so nobody scrolls past the whole story to start.
    story = ["start", "problem", "how", "different", "results", "team"]
    assert [i for i in ids if i in story] == story


def test_the_pipeline_walks_one_real_email_through_four_steps() -> None:
    pipe = block("function pipeHTML(){")
    assert "byId.email_302" in pipe
    assert len(re.findall(r"\[T\(\"\w+\"\),T\(", block("const STEPS = [", "];\n"))) == 4


def test_changing_step_does_not_redraw_the_page() -> None:
    step = branch("step")
    assert "setStep(" in step and "return" in step, "a redraw would reset the scroll on the landing page"
    assert "return" in branch("howto")


def test_the_landing_page_keeps_its_scroll_when_redrawn() -> None:
    assert re.search(r"home:\s*\(q\(\"\.home\"\)", SCRIPT)


def field_counts() -> dict[str, int]:
    js = "\n".join([
        (FRONTEND / "results.js").read_text(encoding="utf-8"),
        block("function fieldCounts(){"),
        "console.log(JSON.stringify(Object.fromEntries(fieldCounts())));",
    ])
    return json.loads(subprocess.run(["node"], input=js, capture_output=True, text=True, check=True).stdout)


def test_the_results_bars_match_the_deck() -> None:
    counts = field_counts()
    assert counts == {"container_count": 19, "port_of_discharge": 13, "gross_weight_kg": 12,
                      "notify_party": 8, "consignee": 7, "shipper": 7, "port_of_loading": 6}
    assert list(counts)[:2] == ["container_count", "port_of_discharge"], "largest first"


def test_every_team_member_has_a_github_link_and_linkedin_only_when_set() -> None:
    team = block("const TEAM = [", "];\n")
    assert len(re.findall(r'gh:"[\w-]+"', team)) == 5
    card = block("function teamHTML(){")
    assert "github.com/" in card and "m.li?" in card


def test_motion_stops_for_people_who_turn_it_off() -> None:
    assert re.search(r"prefers-reduced-motion:reduce\)\{[^}]*\.art \*\{animation:none", INDEX)
