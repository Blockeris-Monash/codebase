"""My mailbox opened on a row of zeros for a second or two, then jumped to the real
counts: the page drew before the first answer from /mailbox came back. Until that
answer, the tiles and the list now say the mailbox is loading."""
from __future__ import annotations

from pathlib import Path

INDEX = (Path(__file__).resolve().parents[1] / "frontend" / "index.html").read_text(encoding="utf-8")


def fetch_body() -> str:
    body = INDEX[INDEX.index("async function fetchLiveMailbox("):]
    return body[:body.index("\n}")]


def test_the_page_knows_whether_the_mailbox_has_answered_yet() -> None:
    assert "liveLoaded:false" in INDEX
    assert "const loadingBox = ()=>S.mailbox===\"live\" && !S.liveLoaded;" in INDEX


def test_every_answer_or_failure_ends_the_loading_state() -> None:
    """A mailbox that never answers must not spin for ever: an error ends it too."""
    body = fetch_body()
    assert body.count("S.liveLoaded = true") >= 3  # no token, 401, and a good answer
    assert "S.liveLoaded = true;" in body[body.index("catch (err)"):]


def test_tiles_and_list_show_loading_instead_of_zeros() -> None:
    kp = INDEX[INDEX.index("const kp = "):]
    kp = kp[:kp.index("\n")]
    assert 'loadingBox()?"\\u2026":count(k)' in kp
    assert 't("Loading your mailbox...")' in INDEX


def test_signing_out_forgets_the_mailbox() -> None:
    wiring = INDEX[INDEX.index("S.authReady = !!window.Store?.onUser?.("):]
    wiring = wiring[:wiring.index("render();")]
    assert "S.liveLoaded = false" in wiring and "S.liveEmails = []" in wiring
