"""Signed in, the inbox still opened on the demo data, so it was unclear whose mail was on
screen. Signing in now lands on My mailbox. The demo is where the evidence lives, so it
stays one click away (#120), as a Demo account in the account menu rather than a switch
beside the search box, which was confusing.

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
    assert 'S.mailbox !== "live")' in wiring
    assert "startPolling()" in wiring


def account_menu() -> str:
    menu = INDEX[INDEX.index("function accountHTML(){"):]
    return menu[:menu.index("\n}")]


def test_there_is_no_demo_switch_in_the_toolbar() -> None:
    """The Demo data / My mailbox pills beside the search box were confusing (#120 follow-up):
    the demo is now an account, picked from the account menu."""
    assert '<div class="seg mbox">' not in INDEX
    assert '<div class="bar"><span class="sbox">' in INDEX


def test_signed_in_the_account_menu_switches_between_your_mail_and_the_demo_account() -> None:
    menu = account_menu()
    assert '"mymailbox", t("My mailbox")' in menu and '"demoacct", t("Demo account")' in menu
    assert 'data-a="signout"' in menu


def test_signed_out_the_inbox_shows_the_demo_account_with_a_way_to_sign_in() -> None:
    menu = account_menu()
    assert 'if(!S.user && isHome())' in menu  # the landing page keeps its plain Sign in button
    assert 'data-a="signin"' in menu


def test_the_landing_page_says_sign_in_with_demo_account() -> None:
    page = home()
    assert page.count('data-a="demoacct">${t("Sign in with demo account")}') == 3
    assert "Open the demo inbox" not in INDEX


def test_the_demo_account_action_opens_the_demo_data() -> None:
    click = INDEX[INDEX.index('else if(a==="demoacct")'):]
    click = click[:click.index("\n")]
    assert 'S.mailbox="demo"' in click and 'location.hash="#/inbox"' in click


def test_a_token_refresh_does_not_pull_you_off_the_demo() -> None:
    """Supabase calls back on every token refresh too; only a fresh sign-in opens My mailbox."""
    wiring = auth_wiring()
    assert "const wasSignedIn = !!S.user;" in wiring
    assert 'if (user && !wasSignedIn && S.mailbox !== "live")' in wiring


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
    assert '<div class="seg mbox">' not in INDEX  # no switch at all
    wiring = INDEX[INDEX.index("S.authReady = !!window.Store?.onUser?.("):]
    assert "if (!user) signInReturn = false;" in wiring[:wiring.index("\n  });")]
    assert 'if(!S.authReady || (!S.user && signInReturn)) return "";' in INDEX  # no Sign in button either


def test_the_landing_page_never_flashes_between_google_and_my_mailbox() -> None:
    """Back from Google, supabase-js clears the token with `location.hash = ''`, which
    fires hashchange: the page drew the landing page for an empty address, then the
    inbox once the sign-in landed. While a sign-in arrives the address is not the
    landing page, and the inbox address is set before the signed-in page is drawn."""
    assert 'const isHome = ()=>!signInReturn && (!location.hash || location.hash==="#/");' in INDEX
    assert "const onHome = isHome();" in INDEX  # render() reads the same rule
    wiring = INDEX[INDEX.index("S.authReady = !!window.Store?.onUser?.("):]
    wiring = wiring[:wiring.index("\n  });")]
    set_inbox = wiring.index('history.replaceState(null, "", location.pathname + "#/inbox");')
    assert set_inbox < wiring.index("render();"), "the inbox address must be set before the first render"
