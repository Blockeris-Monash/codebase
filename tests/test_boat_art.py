"""The logo's waves stay whole through their loop, and the landing ship fishes a document.

The logo's wave line was 120 units long and slides 40 to the left on each loop, so for
the last part of every loop it stopped short of the right side of the logo's circle.
The big ship now has a fishing rod, with a document on the end of the line that
swings gently."""
from __future__ import annotations

import re
from pathlib import Path

INDEX = (Path(__file__).resolve().parents[1] / "frontend" / "index.html").read_text(encoding="utf-8")

CIRCLE_RIGHT = 32 + 27.2  # the logo's clip circle: cx 32, r 27.2
ROLL = 40  # @keyframes roll{to{transform:translateX(-40px)}}


def ship_art() -> str:
    art = INDEX[INDEX.index("const SHIP_ART = (()=>{"):]
    return art[:art.index("})();")]


def test_the_logo_waves_reach_the_right_of_the_circle_all_through_the_loop() -> None:
    assert "@keyframes roll{to{transform:translateX(-40px)}}" in INDEX
    waves = INDEX[INDEX.index('<g class="waves">'):]
    waves = waves[:waves.index("</g>")]
    paths = re.findall(r'd="M(-?\d+) \d+q10-\d 20 0((?:t20 0)+)"', waves)
    assert len(paths) == 2
    for start, repeats in paths:
        end = int(start) + 20 * (1 + repeats.count("t20 0"))
        assert end - ROLL >= CIRCLE_RIGHT, f"wave ends at {end - ROLL} late in the loop"


def test_the_ship_holds_a_fishing_rod_that_bobs_with_it() -> None:
    art = ship_art()
    ship = art[art.index('<g class="shipg">'):]
    assert '<path class="rod"' in ship
    assert '<g class="catch">' in ship


def test_a_document_hangs_on_the_line_and_swings_gently() -> None:
    catch = ship_art()[ship_art().index('<g class="catch">'):]
    assert '<path class="fline"' in catch and '<path class="pg"' in catch
    assert ".art .catch{animation:lpswing" in INDEX
    assert "@keyframes lpswing{" in INDEX
    # Reduced motion already stills everything in the art.
    assert "@media (prefers-reduced-motion:reduce){.art *{animation:none!important}" in INDEX


def test_the_rod_and_its_catch_stay_inside_the_picture() -> None:
    art = ship_art()
    extra = art[art.index('<path class="rod"'):art.index('<rect class="hullc"')]
    xs = [float(x) for x in re.findall(r"[Mh]\s*(-?\d+(?:\.\d+)?)", extra)]
    assert xs and min(xs) >= 0


def test_the_ripple_where_the_document_dips_stays_still() -> None:
    """The ship's foam slides 32 units each loop; a short ripple sliding with it jumped."""
    assert '<path class="ripple"' in ship_art()
    assert ".art .ripple{" in INDEX
    assert ".art .ripple" not in INDEX[INDEX.index(".art .wl,.art .foam{animation:"):][:60]


def test_twinkling_stars_flare_on_the_landing_page_only() -> None:
    assert ".lp-hero .lp-sky .stars .tw,.appbg.live .lp-sky .stars .tw{animation-name:lptwinkle;" in INDEX
    assert "@keyframes lptwinkle{" in INDEX
    assert ".lp-sky .stars circle{fill:#fff}" in INDEX  # still stars are unchanged
    assert ".appbg:not(.live) *{animation:none!important}" in INDEX


def test_the_middle_left_of_the_sky_has_twinkling_stars_too() -> None:
    scene = INDEX[INDEX.index("const SCENE = (()=>{"):]
    scene = scene[:scene.index("})();")]
    assert '<g class="stars">${stars}${leftTw}</g>' in scene
    left = scene[scene.index("const leftTw = ["):scene.index(".map(")]
    points = re.findall(r"\[(\d+),(\d+),", left)
    assert len(points) >= 6 and all(250 < int(x) < 480 for x, _ in points)
    assert '<circle class="tw"' in scene
