"""Popups keep their scroll to themselves, and signing in or out shows it is working.

Scrolling in Help, Contact support moved the inbox behind it: the popup's scroll box
passed the scroll on when it was short or at its end, and nothing held the page still.
Scrolling up there also left the email at its top after Close. Signing out showed
nothing until Supabase answered, and signing in nothing until Google's page opened,
so both looked frozen."""
from __future__ import annotations

import re
from pathlib import Path

INDEX = (Path(__file__).resolve().parents[1] / "frontend" / "index.html").read_text(encoding="utf-8")


def css_rule(selector: str) -> str:
    match = re.search(re.escape(selector) + r"\{([^}]*)\}", INDEX)
    assert match, selector
    return match.group(1)


def click(action: str) -> str:
    line = INDEX[INDEX.index(f'a==="{action}"'):]
    return line[:line.index("\n")]


# --- a popup keeps its scroll ---------------------------------------------------

def test_the_page_behind_a_popup_does_not_scroll() -> None:
    assert "overflow:hidden" in css_rule("html:has(.ov)")


def test_a_popup_passes_no_scroll_to_the_page() -> None:
    assert "overscroll-behavior:contain" in css_rule(".ov")
    assert "overflow:auto" in css_rule(".ov")
    assert "overscroll-behavior:contain" in css_rule(".dlgb")


def test_closing_a_popup_puts_the_email_back_where_it_was() -> None:
    render = INDEX[INDEX.index("function render(){"):INDEX.index('document.getElementById("app").innerHTML')]
    assert "const popup = S.help||S.langDlg||S.reportDlg||S.uploadDlg;" in render
    assert "if(popup && !S.under) S.under = {...keep, at:location.hash+'|'+S.sel};" in render
    assert ("if(!popup && S.under){ if(S.under.at===location.hash+'|'+S.sel) Object.assign(keep, S.under); "
            "S.under = null; }") in render


# --- signing in and out show a loading screen ------------------------------------

def test_signing_out_shows_a_loading_screen_until_it_is_done() -> None:
    line = click("signout")
    assert 'busy(T("Signing out..."))' in line
    assert "window.Store?.signOut()?.finally?.(()=>busy(null))" in line


def test_signing_in_shows_a_loading_screen_until_google_opens() -> None:
    for action in ("signin", "reportsignin"):
        assert "startSignIn();" in click(action), action
    start = INDEX[INDEX.index("function startSignIn(){"):]
    start = start[:start.index("\n}\n")]
    assert 'busy(T("Opening Google sign-in..."));' in start
    assert "if(ok===false) busy(null);" in start


def test_a_loading_screen_never_stays_forever() -> None:
    fn = INDEX[INDEX.index("function busy(text){"):]
    fn = fn[:fn.index("\n}\n")]
    assert "clearTimeout(busyTimer);" in fn
    assert "busyTimer = setTimeout(()=>busy(null), 15000);" in fn
    # Back from Google with the browser's Back button, the page is shown as it was left.
    assert 'addEventListener("pageshow", ev=>{ if(ev.persisted) busy(null); });' in INDEX


def test_the_sign_in_callback_ends_the_loading_screen() -> None:
    wiring = INDEX[INDEX.index("S.authReady = !!window.Store?.onUser?.("):]
    assert "S.busy = null;" in wiring[:wiring.index("render();")]


def test_the_loading_screen_is_drawn_and_announced() -> None:
    assert "${S.busy?busyHTML():\"\"}" in INDEX
    body = INDEX[INDEX.index("function busyHTML(){"):]
    body = body[:body.index("\n}\n")]
    assert 'role="status"' in body and 'aria-live="polite"' in body
    assert "t(S.busy)" in body
