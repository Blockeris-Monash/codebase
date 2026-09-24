"""Sign in with Google (task 3), through Supabase.

The Google client ID and secret live in the Supabase dashboard, so the page only
asks Supabase for "google". Signed out, offline or unconfigured, the page must look
and behave exactly as before: no button, no error, marks still saved locally.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

FRONTEND = Path(__file__).resolve().parents[1] / "frontend"
INDEX = (FRONTEND / "index.html").read_text(encoding="utf-8")
STORE = (FRONTEND / "store.js").read_text(encoding="utf-8")


def test_no_google_client_id_or_secret_is_in_the_page() -> None:
    """Both belong in Supabase. A secret in the frontend ships to every browser."""
    for path in FRONTEND.glob("*.js"):
        text = path.read_text(encoding="utf-8")
        assert "apps.googleusercontent.com" not in text, path.name
        assert "GOCSPX" not in text, path.name


def test_sign_in_asks_supabase_for_google_and_comes_back_to_this_page() -> None:
    assert 'provider: "google"' in STORE
    assert "redirectTo: location.origin + location.pathname" in STORE


@pytest.mark.parametrize("fn", ["signIn", "signOut", "onUser"])
def test_each_sign_in_function_gives_up_quietly_without_a_client(fn: str) -> None:
    body = STORE[STORE.index(f"function {fn}("):]
    body = body[:body.index("\n  }")]

    assert "if (!c) return" in body, f"{fn} does not check for a client"


def test_sign_in_failures_are_contained() -> None:
    for fn in ("signIn", "signOut"):
        body = STORE[STORE.index(f"function {fn}("):]
        body = body[:body.index("\n  }")]
        assert "try {" in body and "catch" in body, fn


def test_the_button_stays_hidden_until_sign_in_is_available() -> None:
    """Offline or unconfigured, the top bar is exactly as before."""
    helper = INDEX[INDEX.index("function accountHTML(){"):INDEX.index("\nfunction render(){")]

    assert 'if(!S.authReady || (!S.user && signInReturn)) return "";' in helper
    assert "S.authReady = !!window.Store?.onUser?.(" in INDEX


def test_sign_in_is_wired_after_the_supabase_module_has_run() -> None:
    """Module scripts run after the page's own scripts but before DOMContentLoaded."""
    wiring = INDEX[INDEX.index('document.addEventListener("DOMContentLoaded"'):]

    assert "window.Store?.onUser" in wiring


def test_saved_marks_are_pulled_after_sign_in_outside_the_auth_callback() -> None:
    """supabase-js must not be called from inside its own auth callback, or it can hang."""
    wiring = INDEX[INDEX.index('document.addEventListener("DOMContentLoaded"'):]
    wiring = wiring[:wiring.index("</script>")]

    assert 'event==="INITIAL_SESSION"||event==="SIGNED_IN"' in wiring
    assert wiring.index("setTimeout(") < wiring.index("window.Store?.pull(")


def test_the_new_sign_in_calls_are_guarded_against_a_missing_store() -> None:
    """`Store?.x` still throws when store.js never loaded; `window.Store?.x` does not."""
    for call in ("signIn", "signOut", "onUser"):
        uses = re.findall(r"(\S*)Store\?\." + call, INDEX)
        assert uses and all(u.endswith("window.") for u in uses), call
