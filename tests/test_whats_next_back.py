"""What's next, opened from the landing page, sent Back to the inbox: its button was
hard-wired to the inbox. It now goes back to wherever the reader came from."""
from __future__ import annotations

from pathlib import Path

INDEX = (Path(__file__).resolve().parents[1] / "frontend" / "index.html").read_text(encoding="utf-8")


def test_opening_whats_next_remembers_where_the_reader_was() -> None:
    assert 'else if(a==="next"){ S.help=false; S.nextFrom=location.hash;' in INDEX


def test_back_returns_there_and_says_where() -> None:
    page = INDEX[INDEX.index("function nextPage(){"):]
    page = page[:page.index("<h1>")]
    assert 'data-a="nextback"' in page and 'data-a="inbox"' not in page
    assert 'fromHome?t("Back to home"):t("Back to inbox")' in page
    assert 'else if(a==="nextback"){ location.hash = fromHomeHash() ? "#/" : "#/inbox";' in INDEX
