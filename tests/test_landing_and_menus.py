"""Landing page and menu fixes after the upload feature went live.

1. A reload lost the Google token (kept in memory only), so a signed-in person saw
   "Sign in" in a bar above their own mailbox. It now lasts the tab, for its hour.
2. The account menu no longer lists Upload SI and BL files (the landing card and the
   Manual uploads bar have it).
3. Get started shows the same three cards signed in, on the demo account, or signed out.
4. The top bar stops wrapping on mid-size screens, so a menu never opens off the edge.
5. The Sort by list follows the theme.
"""
from __future__ import annotations

from pathlib import Path

FRONTEND = Path(__file__).resolve().parents[1] / "frontend"
INDEX = (FRONTEND / "index.html").read_text(encoding="utf-8")
STORE = (FRONTEND / "store.js").read_text(encoding="utf-8")


def block(source: str, start: str, end: str = "\n}\n") -> str:
    at = source.index(start)
    return source[at:source.index(end, at) + len(end)]


def test_the_google_token_survives_a_reload_for_its_hour_in_this_tab_only() -> None:
    assert "sessionStorage.setItem(TOKEN_KEY" in STORE
    assert "localStorage.setItem(TOKEN_KEY" not in STORE
    token = block(STORE, "  function googleToken() {", "\n  }\n")
    assert "Date.now()" in token and "sessionStorage.removeItem(TOKEN_KEY)" in token
    assert "sessionStorage.removeItem(TOKEN_KEY)" in block(STORE, "  async function signOut() {", "\n  }\n")


def test_signed_in_the_bar_asks_to_reconnect_gmail_not_to_sign_in() -> None:
    bar = block(INDEX, "function mailboxBarHTML(){")
    assert 't("Reconnect Gmail")' in bar and 't("Sign in")' not in bar
    assert "Sign in with Google again to see your mailbox." not in INDEX


def test_the_account_menu_does_not_offer_uploading() -> None:
    menu = block(INDEX, "function accountHTML(){")
    assert 'data-a="upload"' not in menu
    assert '"uploadsbox"' in menu  # the Manual uploads box is still reachable


def test_get_started_shows_the_same_three_cards_for_everyone() -> None:
    home = block(INDEX, "function homePage(){")
    start = home[home.index('<section id="start"'):]
    start = start[:start.index("</section>")]
    assert '${u?"":' not in start
    assert start.count('<div class="opt ') == 3
    gmail = block(INDEX, "function homePage(){")
    assert "Signed in as {name}." not in gmail


def test_the_top_bar_hides_labels_before_it_would_wrap() -> None:
    fit = block(INDEX, "function fitTop(){")
    assert 'top.classList.add("t1")' in fit and 'top.classList.add("t2")' in fit
    assert ".top.t1>.mute,.top.t2 .hb .lbl{display:none}" in INDEX
    assert "  fitTop();\n" in block(INDEX, "function render(){")
    assert 'addEventListener("resize", fitTop);' in INDEX
    assert ".menu{" in INDEX and "max-width:calc(100vw - 32px)" in INDEX


def test_the_sort_list_options_follow_the_theme() -> None:
    assert ".pick select option{background:var(--panel);color:var(--ink)}" in INDEX


# ---------------------------------------------------------------- straight after sign-in
#
# The first /mailbox answer after a sign-in usually holds no checked email yet, only
# X-Mailbox-Pending. That showed "All done in this folder" with zeros, a "Checking N new
# emails" bar pushed the whole page down, and "Loading your mailbox" showed twice.

def test_the_mailbox_is_still_loading_while_its_first_emails_are_being_checked() -> None:
    assert 'const loadingBox = ()=>S.mailbox==="live" && (!S.liveLoaded || (!S.liveEmails.length && S.pending>0));' in INDEX


def test_checking_new_emails_is_not_a_bar_above_the_page() -> None:
    bar = block(INDEX, "function mailboxBarHTML(){")
    assert "S.pending" not in bar and "Checking {n} new emails..." not in bar
    render = block(INDEX, "function render(){")
    assert "checkingHTML()" in render


def test_loading_your_mailbox_is_said_once() -> None:
    render = block(INDEX, "function render(){")
    assert render.count('t("Loading your mailbox...")') == 0
    assert "loadingHTML()" in render
