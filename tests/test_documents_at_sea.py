"""The landing scene: a ship with containers and documents that sits in the water, a
calm pace, and living birds. Floating paper was tried and removed: it read as rubbish
in the sea."""
from __future__ import annotations

import re
from pathlib import Path

INDEX = (Path(__file__).resolve().parents[1] / "frontend" / "index.html").read_text(encoding="utf-8")


def block(start: str) -> str:
    part = INDEX[INDEX.index(start):]
    return part[:part.index("})();")]


def test_the_ship_carries_containers_mixed_with_documents() -> None:
    ship = block("const SHIP_ART = (()=>{")
    assert 'class="cb ${c}"' in ship and "url(#corr)" in ship, "containers"
    assert 'class="cargo' in ship and 'class="fold"' in ship and 'class="stamp' in ship, "documents"
    assert ship.count(",box]") >= 3 and ship.count(",doc]") >= 3, "a mix on both rows"


def test_no_paper_floats_on_the_sea() -> None:
    for gone in ("FLOATERS", "floater", "flclip", "--float"):
        assert gone not in INDEX, gone


def test_the_ship_sits_in_the_water_not_on_a_hard_edge() -> None:
    """The hull's bottom was a straight cut on the sea. Water in front of it, fading down,
    with a moving foam line, puts the ship in the sea."""
    ship = block("const SHIP_ART = (()=>{")
    assert 'class="wl"' in ship and 'class="foam"' in ship and 'id="wlg"' in ship
    assert "stop-color:var(--se1)" in ship, "the sea's own colour, in both themes"
    assert ship.index("</g>") < ship.index('class="wl"'), "outside the bobbing hull, so the water stays level"
    assert ".art .wl,.art .foam{animation:lpwave" in INDEX
    assert '<g mask="url(#wlm)"><path class="wl"' in ship, "faded at both ends, so no box shows"


def test_the_waterline_loops_seamlessly() -> None:
    shift = int(re.search(r"@keyframes lpwave\{to\{transform:translateX\(-(\d+)px\)\}\}", INDEX).group(1))
    assert '"q8-3 16 0t16 0"' in block("const SHIP_ART = (()=>{") and shift == 32


def test_the_ship_sails_at_a_calm_pace() -> None:
    seconds = int(re.search(r"animation:lpsail (\d+)s linear infinite", INDEX).group(1))
    assert seconds >= 60


def test_the_birds_flap_and_glide() -> None:
    assert re.search(r"\.lp-sky \.gull\{[^}]*animation:lpflap", INDEX)
    assert ".lp-sky .gullg{animation:lpglide" in INDEX
    assert ".lp-sky .gullg," in INDEX, "glide resumes from the page clock after a redraw"


def test_all_of_it_holds_still_for_reduced_motion() -> None:
    assert ".lp-deco *,.lp-sky *,.art *{animation:none!important}" in INDEX
