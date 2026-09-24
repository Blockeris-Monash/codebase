"""Signed in, the top of the landing page offered only the demo inbox; the way into
My mailbox sat far down, in "Where is your mail?". The hero now leads with it, and a
signed-in account is offered only its own mailbox, not the demo inbox."""
from __future__ import annotations

from pathlib import Path

INDEX = (Path(__file__).resolve().parents[1] / "frontend" / "index.html").read_text(encoding="utf-8")


def hero() -> str:
    home = INDEX[INDEX.index("function homePage(){"):]
    return home[home.index('<section class="lp-hero">'):home.index("</section>")]


def test_signed_in_the_hero_leads_with_my_mailbox() -> None:
    assert 'u?`<button class="btn" data-a="mymailbox">${t("Open my mailbox")}</button>`' in hero()


def test_signed_out_the_hero_is_as_before() -> None:
    assert ':`<button class="btn" data-a="inbox">${t("Open the demo inbox")}</button>`' in hero()
    assert 'data-a="howto"' in hero()
