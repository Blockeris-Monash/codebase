"""Why a sign-in did not finish has to reach the person, not the console.

Google refuses an account that is not on the OAuth consent screen's test-user
list, and it refuses *after* the account chooser. Supabase hands that refusal
back as `error` and `error_description` on the return URL. Nothing read them,
so the page simply reappeared signed out and the reason sat in the address bar
where nobody looks - which is exactly how a working configuration and a broken
one came to look identical.
"""
from __future__ import annotations

from pathlib import Path

import pytest

FRONTEND = Path(__file__).resolve().parents[1] / "frontend"
INDEX = (FRONTEND / "index.html").read_text(encoding="utf-8")
STORE = (FRONTEND / "store.js").read_text(encoding="utf-8")


def test_the_refusal_is_read_from_the_url() -> None:
    """Supabase puts it in the query on some flows and the fragment on others,
    so reading only one of them misses half the failures."""
    body = STORE[STORE.index("function authError("):]
    body = body[:body.index("\n  }")]

    assert "location.search" in body and "location.hash" in body
    assert "error_description" in body


def test_the_reason_is_cleared_once_it_has_been_read() -> None:
    """Left in the address bar it reappears on every reload, and a shared link
    carries someone else's failure."""
    body = STORE[STORE.index("function authError("):]

    assert "history.replaceState" in body[:body.index("\n  }")]


def test_no_error_in_the_url_means_no_banner() -> None:
    body = STORE[STORE.index("function authError("):]

    assert "if (!code) return null;" in body[:body.index("\n  }")]


def test_the_account_not_on_the_tester_list_gets_its_own_sentence() -> None:
    """`access_denied` is the one a team will actually hit, and the generic
    text does not tell them what to do about it."""
    assert 'ACCESS_DENIED = "access_denied"' in STORE
    assert "tester list" in INDEX
    assert "Ask the team to add it" in INDEX


def test_any_other_failure_still_says_something() -> None:
    """A reason we have not seen before must not fall through silently."""
    assert "Sign-in did not finish: {reason}" in INDEX


def test_the_banner_is_rendered_where_it_cannot_be_missed() -> None:
    assert "${signInErrorHTML()}<div class=\"top\">" in INDEX
    assert 'role="alert"' in INDEX[INDEX.index("function signInErrorHTML"):][:900]


def test_the_message_can_be_dismissed() -> None:
    assert 'data-a="dismisserr"' in INDEX
    assert 'a==="dismisserr"' in INDEX


def test_it_is_read_once_at_load_beside_the_rest_of_the_auth_wiring() -> None:
    assert "S.authErr = window.Store?.authError?.() || null;" in INDEX
    assert INDEX.index("S.authErr = window.Store") < INDEX.index("S.authReady = !!window.Store")


@pytest.mark.parametrize("token", ["authError", "ACCESS_DENIED"])
def test_the_helper_is_exported(token: str) -> None:
    exported = STORE[STORE.index("window.Store = {"):]

    assert token in exported[:400]


def test_a_missing_store_does_not_break_the_page() -> None:
    """store.js is one more script that can fail to load."""
    assert "window.Store?.authError?.()" in INDEX
