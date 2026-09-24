"""The sky and sea design reaches the screens that missed it: What's next moves like the
landing page, and Help opens on a strip of the same scene. Work screens stay still."""
from __future__ import annotations

from pathlib import Path

INDEX = (Path(__file__).resolve().parents[1] / "frontend" / "index.html").read_text(encoding="utf-8")


def test_whats_next_has_a_moving_sky() -> None:
    assert "${onHome?\"\":onNext?APPBG_LIVE:APPBG}" in INDEX
    assert '<div class="appbg live" aria-hidden="true">${SCENE}</div>' in INDEX


def test_the_inbox_sky_still_holds_still() -> None:
    """Reviewers look at the inbox all day; only What's next moves."""
    assert ".appbg:not(.live) *{animation:none!important}" in INDEX


def test_help_opens_on_the_scene_and_it_stays_still() -> None:
    help_ = INDEX[INDEX.index("function helpHTML(){"):]
    help_ = help_[:help_.index("\n}")]
    assert '<div class="dlgh sky">${SCENE}<h2>' in help_
    assert ".dlgh.sky .lp-sky *{animation:none!important}" in INDEX


def test_the_help_backdrop_is_night_blue_and_blurred() -> None:
    assert ".ov{position:fixed;inset:0;background:rgba(20,26,51,.42);backdrop-filter:blur(3px);" in INDEX


def test_the_help_body_carries_on_from_the_horizon() -> None:
    """The body under the scene header was a flat panel. It now starts in a deep-water tint that
    fades to the panel, with a faint sunset glow at the foot; text sits on near-plain panel."""
    rule = INDEX[INDEX.index(".dlg.wide{overflow:hidden;"):]
    rule = rule[:rule.index("}")]
    assert "linear-gradient(180deg,var(--dlg-top) 0,var(--panel)" in rule and "var(--sk4) 22%" in rule
    assert INDEX.count("--dlg-top:") == 3, "its own top colour by day and at night"


def test_the_help_body_scrolls_under_a_fixed_header() -> None:
    """The popup hides its overflow (to clip the scene header), so the body must take the
    remaining height and scroll on its own; without that, Guide and Contact support were cut off."""
    assert ".dlg.wide{overflow:hidden;display:flex;flex-direction:column;" in INDEX
    assert ".dlg.wide .dlgb{flex:1;min-height:0;overflow:auto}" in INDEX
