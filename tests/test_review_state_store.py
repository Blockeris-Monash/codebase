"""What a reviewer marked has to survive a change of browser.

The marks lived only in localStorage, which is per-device: forty emails marked
on the demo laptop and the phone shows none of them. They now mirror to
Postgres, keyed to whoever is signed in.

The risk in that change is not the database - it is breaking the promise the
README opens with, that the page works "with no backend, no key and no
network". These tests hold that promise: localStorage stays synchronous and
authoritative, and nothing about the database can stop a mark registering.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

FRONTEND = Path(__file__).resolve().parents[1] / "frontend"
INDEX = (FRONTEND / "index.html").read_text(encoding="utf-8")
STORE = (FRONTEND / "store.js").read_text(encoding="utf-8")
CONFIG = (FRONTEND / "config.js").read_text(encoding="utf-8")
SW = (FRONTEND / "sw.js").read_text(encoding="utf-8")


def test_a_failed_store_cannot_stop_an_email_being_marked() -> None:
    """store.js is one more script that can fail to load. If it does, `Store`
    is undefined, and an unguarded call would throw inside the click handler
    and take marking down with it."""
    unguarded = re.findall(r"(?<!\?)\bStore\.", INDEX)

    assert not unguarded, f"Store used without optional chaining: {unguarded}"
    assert INDEX.count("Store?.") >= 5


def test_the_marks_are_still_read_synchronously_from_the_browser() -> None:
    """The page builds its state at load with `marks: loadMarks()`. If that
    became a network read the whole startup path would have to be async, and a
    paused free-tier database would delay first paint."""
    assert 'function loadMarks(){ try{ return JSON.parse(localStorage.getItem("blockeris.marks")' in INDEX
    assert "marks:loadMarks()" in INDEX.replace(" ", "")


def test_every_local_write_still_happens_before_any_push() -> None:
    """Local first, database second - so an offline reviewer still sees the
    mark they just made."""
    for local, pushed in (("saveMarks(); Store?.pushMark", "pushMark"),
                          ("saveSent(); saveMarks(); Store?.pushReply", "pushReply")):
        assert local in INDEX, f"{pushed} must come after the local save"


def test_the_pull_runs_after_the_first_paint() -> None:
    """Reading the account's marks must not delay rendering."""
    assert INDEX.index("\nrender();") < INDEX.index("Store?.pull(")


@pytest.mark.parametrize("fn", ["pushMark", "pushReply", "pushReport", "pull"])
def test_every_store_function_gives_up_quietly_when_signed_out(fn: str) -> None:
    """Signed out, unconfigured or offline, the app must behave exactly as it
    did before - no thrown error, no blocking dialog."""
    body = STORE[STORE.index(f"function {fn}("):]
    body = body[:body.index("\n  }")]

    assert "if (!c" in body or "if (!client" in body, f"{fn} does not check for a client"
    assert "try {" in body and "catch" in body, f"{fn} does not contain its own failures"


def test_the_committed_key_is_a_publishable_one_not_a_secret() -> None:
    """config.js ships to every browser. A service_role or secret key there
    bypasses row-level security entirely and exposes every row."""
    assert "service_role" not in CONFIG
    assert "sb_secret" not in CONFIG
    assert "SUPABASE_ANON_KEY" in CONFIG


def test_the_shell_changed_so_the_service_worker_version_moved() -> None:
    """sw.js caches the shell. Ship a new index.html on the old version and
    returning visitors keep the old page."""
    assert "ship-happens-v3" in SW


def test_the_demo_source_matches_the_database_constraint() -> None:
    """`source` is CHECK (source in ('demo','mailbox')). A mismatch here fails
    every insert at runtime with a constraint violation nobody will read."""
    migration = (Path(__file__).resolve().parents[1]
                 / "backend/db/migrations/0001_init.sql").read_text(encoding="utf-8")

    assert "check (source in ('demo', 'mailbox'))" in migration
    assert 'const DEMO = "demo";' in STORE


def test_the_marks_the_store_sends_are_the_ones_the_table_allows() -> None:
    """`mark` is CHECK (mark in ('ok','back'))."""
    migration = (Path(__file__).resolve().parents[1]
                 / "backend/db/migrations/0001_init.sql").read_text(encoding="utf-8")

    assert "check (mark in ('ok', 'back'))" in migration
    assert 'MARK_OK = "ok"' in STORE and 'MARK_BACK = "back"' in STORE
