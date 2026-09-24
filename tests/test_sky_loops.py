"""The waves jumped at the end of each loop and the clouds barely moved.

Waves: the lines moved 360 units per loop, but their shape repeated only every 720, so
each loop ended on a different curve. They are now drawn with a 360-unit period.
Clouds: they rocked 60 units back and forth over 30 s or more. They now drift right
across the sky and come back in from the left while out of sight."""
from __future__ import annotations

import re
from pathlib import Path

INDEX = (Path(__file__).resolve().parents[1] / "frontend" / "index.html").read_text(encoding="utf-8")
SHIFT = int(re.search(r"@keyframes lpwv\{to\{transform:translateX\(-(\d+)px\)\}\}", INDEX).group(1))


def test_the_wave_repeats_exactly_once_per_loop() -> None:
    wave = INDEX[INDEX.index("const wavePath"):]
    wave = wave[:wave.index("\n")]
    period = re.search(r"q(\d+)-?\d+ (\d+) 0t(\d+) 0", wave)
    assert period and int(period.group(2)) + int(period.group(3)) == SHIFT


def test_the_wave_is_long_enough_to_cover_the_sky_while_it_moves() -> None:
    reps = int(re.search(r"\.repeat\((\d+)\)", INDEX[INDEX.index("const wavePath"):]).group(1))
    assert reps * SHIFT >= 1440 + SHIFT


def test_clouds_drift_one_way_and_wrap_out_of_sight() -> None:
    assert "@keyframes lpcloud{from{transform:translateX(var(--a))}to{transform:translateX(var(--b))}}" in INDEX
    rule = re.search(r"\.lp-sky \.cloud\{animation:([^}]*)\}", INDEX).group(1)
    assert "linear infinite" in rule and "alternate" not in rule


def test_clouds_resume_from_the_page_clock_at_their_own_place() -> None:
    """The page is rebuilt on every click; each cloud must carry on where it was."""
    assert ".lp-sky .cloud{animation-delay:calc(var(--t,0) * -1s - var(--o,0s))!important}" in INDEX


def test_clouds_and_waves_move_at_a_visible_pace() -> None:
    clouds = re.search(r"const CLOUDS = (\[\[.*?\]\]);", INDEX).group(1)
    durations = [float(c.split(",")[3]) for c in re.findall(r"\[([^\[\]]+)\]", clouds)]
    assert durations and 100 <= min(durations) and max(durations) <= 160, "drifting, neither stuck nor racing"
    assert ".lp-sky .wv{animation-duration:7s}.lp-sky .w2{animation-duration:10s}" in INDEX


def test_the_night_sky_has_faint_stars_in_the_middle_too() -> None:
    """The middle used to be left empty. Stars there are small and faint so the headline stays readable."""
    assert 'if(x>330&&x<1110&&y>30) return ""' not in INDEX
    assert "mid=x>330&&x<1110&&y>30" in INDEX and ".lp-sky .stars .mid{opacity:.5}" in INDEX


def test_a_second_shooting_star_crosses_near_the_middle() -> None:
    assert '<path class="shoot s2" d="M900 4l-170 30"/>' in INDEX
    assert ".lp-sky .shoot.s2{animation-duration:13s;animation-delay:calc(7.5s - var(--t,0) * 1s)}" in INDEX
