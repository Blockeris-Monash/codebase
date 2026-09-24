"""Signed in, the inbox still opened on the demo data and offered a Demo data / My mailbox
switch, so it was unclear whose mail was on screen. A signed-in account now sees only its
own mailbox; the demo stays for visitors who are not signed in.

"Check again with AI" is gone too: My mailbox already runs every new email through the
live pipeline, so re-running a saved demo result added nothing."""
from __future__ import annotations

from pathlib import Path

INDEX = (Path(__file__).resolve().parents[1] / "frontend" / "index.html").read_text(encoding="utf-8")


def auth_wiring() -> str:
    wiring = INDEX[INDEX.index("S.authReady = !!window.Store?.onUser?.("):]
    return wiring[:wiring.index("render();")]


def home() -> str:
    return INDEX[INDEX.index("function homePage(){"):INDEX.index("</footer></main>`;")]


def test_signing_in_opens_my_mailbox_and_starts_fetching_it() -> None:
    wiring = auth_wiring()
    assert 'if (user && S.mailbox !== "live")' in wiring
    assert "startPolling()" in wiring


def test_the_demo_switch_only_shows_when_signed_out() -> None:
    assert '${S.user||signInReturn?"":`<div class="seg mbox">' in INDEX


def test_signed_in_the_landing_page_offers_no_demo_inbox() -> None:
    page = home()
    hero = page[page.index('<section class="lp-hero">'):page.index("</section>")]
    assert 'u?`<button class="btn" data-a="mymailbox">${t("Open my mailbox")}</button>`' in hero
    assert '${u?"":`<div class="opt main top-acc">' in page
    foot = page[page.index('<div class="lp-links">'):]
    assert 'u?`<button class="ghost" data-a="mymailbox">${t("Open my mailbox")}</button>`' in foot


def test_check_again_with_ai_is_gone() -> None:
    for gone in ("Check again with AI", "function recheck(", "canRecheck", 'a==="recheck"', "S.live["):
        assert gone not in INDEX, gone


def test_coming_back_from_google_goes_straight_to_my_mailbox() -> None:
    """Google returns to the page with #access_token=... in the address. The page drew the
    inbox for that unknown address, then Supabase cleared it and the page jumped to the
    landing page. The return is now noticed before Supabase clears it, drawn as My mailbox
    loading, and the address is set to the inbox once the sign-in lands."""
    assert "const FROM_SIGN_IN = /[#&]access_token=/.test(location.hash);" in INDEX
    assert 'mailbox:FROM_SIGN_IN?"live":"demo"' in INDEX
    wiring = INDEX[INDEX.index("S.authReady = !!window.Store?.onUser?.("):]
    wiring = wiring[:wiring.index("\n  });")]
    assert 'history.replaceState(null, "", location.pathname + "#/inbox")' in wiring


def test_the_screen_while_a_sign_in_arrives_shows_no_nan_and_no_demo_switch() -> None:
    """Back from Google, before the account loaded, the tiles read NaN (the count-up
    counted towards the loading dots), and the Demo data / My mailbox switch and the Sign in
    button showed."""
    count_up = INDEX[INDEX.index("function countUp(){"):]
    count_up = count_up[:count_up.index("\n}")]
    assert '.filter(t=>/^\\d+$/.test(t.textContent))' in count_up
    assert '${S.user||signInReturn?"":`<div class="seg mbox">' in INDEX
    wiring = INDEX[INDEX.index("S.authReady = !!window.Store?.onUser?.("):]
    assert "if (!user) signInReturn = false;" in wiring[:wiring.index("\n  });")]
    assert 'if(!S.authReady || (!S.user && signInReturn)) return "";' in INDEX  # no Sign in button either
