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
