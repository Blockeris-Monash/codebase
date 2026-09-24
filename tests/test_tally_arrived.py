"""At 100% the progress boat sat on top of the port flag and the two icons overlapped.
When every email is done, the boat has arrived: it takes the flag's place, in green."""
from __future__ import annotations

from pathlib import Path

INDEX = (Path(__file__).resolve().parents[1] / "frontend" / "index.html").read_text(encoding="utf-8")


def test_a_finished_voyage_is_marked_arrived() -> None:
    tally = INDEX[INDEX.index("function tallyHTML(){"):]
    tally = tally[:tally.index("\n}")]
    assert '<span class="voy ${total&&done===total?"arrived":""}"' in tally


def test_the_arrived_boat_replaces_the_flag_instead_of_covering_it() -> None:
    assert ".tally .voy.arrived .port{display:none}" in INDEX
    assert ".tally .voy.arrived .boat{left:calc(100% - 11px);background:var(--ok)}" in INDEX
