"""The review app carries the landing page's night-voyage look, while the reading areas stay light.

The top bar is the night sky with a sunset horizon, the logo and tile numbers use the stencil lettering,
progress is a voyage with the ship moving toward port, and the empty states are a small sea scene.
"""
from __future__ import annotations

import re
from pathlib import Path

INDEX = (Path(__file__).resolve().parents[1] / "frontend" / "index.html").read_text(encoding="utf-8")
SCRIPT = INDEX[INDEX.index("<script>\n"):]


def block(start: str) -> str:
    at = SCRIPT.index(start)
    return SCRIPT[at:SCRIPT.index("\n}\n", at) + 3]


def test_the_top_bar_is_the_night_sky() -> None:
    assert re.search(r"\.top\{background:var\(--tb\)", INDEX) and "--tb:linear-gradient(100deg,#141a33" in INDEX
    assert re.search(r"\.top \.logo\{[^}]*Big Shoulders Stencil", INDEX)


def test_progress_is_a_voyage_toward_port() -> None:
    tally = block("function tallyHTML(){")
    assert 'class="boat"' in tally and 'class="port"' in tally


def test_the_empty_states_are_a_sea_scene() -> None:
    assert "sceneCard(" in block("function allDoneHTML(){")
    pane = re.search(r"const pane = .*", SCRIPT).group(0)
    assert "sceneCard(" in pane


def test_the_sky_and_sea_sit_behind_the_app() -> None:
    render = block("function render(){")
    assert "onHome?\"\":onNext?APPBG_LIVE:APPBG" in render.replace(" ", "")
    assert re.search(r"\.appbg\{position:fixed;inset:0;z-index:0;pointer-events:none", INDEX)


def test_a_redraw_does_not_restart_the_scene() -> None:
    """Every click rebuilds the page; the scene's loops resume from the page clock instead of restarting."""
    assert 'setProperty("--t"' in block("function render(){")
    assert re.search(r"\.lp-hero \.lp-sailer\{[^}]*animation-delay:calc\(var\(--t,0\) \* -1s\)", INDEX)


def test_the_hero_sea_fades_into_the_page() -> None:
    assert re.search(r"\.lp-hero \.lp-sky\{[^}]*mask-image:linear-gradient", INDEX)


def test_inside_pages_have_a_home_button() -> None:
    assert '!onHome?`<button class="ghost hb" data-a="home"' in SCRIPT


def test_the_app_background_is_still_and_faint() -> None:
    """Behind the work it should be calm: no motion, and faded so the boxes stand out.
    Only What's next, which is read rather than worked in, moves (.live)."""
    rule = re.search(r"\.appbg\{position:fixed;inset:0;z-index:0;pointer-events:none;opacity:(\.\d+)\}", INDEX)
    assert rule and float(rule.group(1)) <= 0.5
    assert re.search(r"\.appbg:not\(\.live\) \*\{animation:none!important\}", INDEX)
