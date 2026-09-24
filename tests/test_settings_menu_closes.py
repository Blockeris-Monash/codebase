"""Picking a language closed the Settings menu, but picking Light or Dark Mode left it open,
with no obvious way to close it. Both choices now close the menu."""
from __future__ import annotations

from pathlib import Path

INDEX = (Path(__file__).resolve().parents[1] / "frontend" / "index.html").read_text(encoding="utf-8")


def test_picking_a_colour_mode_closes_the_menu() -> None:
    assert 'if(a==="theme"){ document.documentElement.dataset.theme = k; S.langMenu=false; }' in INDEX


def test_picking_a_language_still_closes_it() -> None:
    assert 'else if(a==="langpick"){ S.langMenu=false; setLang(k); }' in INDEX
