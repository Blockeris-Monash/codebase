"""The ship carries documents, not containers, and loose documents float on the sea:
the product checks paperwork, so the picture should show paperwork."""
from __future__ import annotations

from pathlib import Path

INDEX = (Path(__file__).resolve().parents[1] / "frontend" / "index.html").read_text(encoding="utf-8")


def block(start: str) -> str:
    part = INDEX[INDEX.index(start):]
    return part[:part.index("})();")]


def test_the_ship_carries_documents_not_containers() -> None:
    ship = block("const SHIP_ART = (()=>{")
    assert "corr" not in ship, "container ridges are gone"
    assert 'class="cargo' in ship and 'class="fold"' in ship and 'class="stamp' in ship


def test_documents_float_on_the_sea() -> None:
    scene = block("const SCENE = (()=>{")
    assert scene.count('class="floater"') >= 1 and "FLOATERS" in INDEX
    assert ".lp-sky .floater{" in INDEX


def test_the_floating_documents_keep_still_where_motion_is_off() -> None:
    """The app background and reduced motion already stop every animation in the sky."""
    assert ".appbg *{animation:none!important}" in INDEX
    assert ".lp-deco *,.lp-sky *{animation:none!important}" in INDEX
