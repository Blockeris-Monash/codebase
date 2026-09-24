"""The ship carries containers mixed with documents, and loose documents float on the sea:
the product checks the paperwork that travels with the cargo."""
from __future__ import annotations

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


def test_documents_float_on_the_sea() -> None:
    scene = block("const SCENE = (()=>{")
    assert scene.count('class="floater"') >= 1 and "FLOATERS" in INDEX
    assert ".lp-sky .floater .rock{" in INDEX


def test_the_floating_documents_keep_still_where_motion_is_off() -> None:
    """The app background and reduced motion already stop every animation in the sky."""
    assert ".appbg *{animation:none!important}" in INDEX
    assert ".lp-deco *,.lp-sky *{animation:none!important}" in INDEX


def test_a_floating_document_sits_in_the_water_not_on_top_of_it() -> None:
    """They looked like flat pictures pasted on the sea. Each now lies at an angle, its lower
    edge hidden under a waterline, with a wave crest in front, a ripple, and a slow rock."""
    scene = block("const SCENE = (()=>{")
    assert '<clipPath id="flclip">' in scene and 'clip-path="url(#flclip)"' in scene
    assert 'class="crest"' in scene and 'class="ripple"' in scene and 'class="rock"' in scene
    assert "skewX(" in scene and "scale(1 .55)" in scene, "seen lying down, in perspective"


def test_floating_documents_are_dimmer_at_night() -> None:
    assert INDEX.count("--float:") >= 3, "a colour for day, and for night in both dark-mode rules"
