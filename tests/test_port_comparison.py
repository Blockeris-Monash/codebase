"""Two different ports never compare as the same port (#147 A3).

The comparator deleted every bare five-letter word as if it were a UN/LOCODE, then
counted any subset of the remaining words as a match. KLANG, NORTH, SOUTH and CHINA
are all five letters, so PORT KLANG matched PORT DICKSON. The dataset never showed it
because no planted defect changes one word of a two-word port.

Two holes were left after that fix. A real city of five letters that starts with a country
code (TOKYO starts with TO, Tonga; PERTH with PE, Peru) was still deleted as a LOCODE, so
"TOKYO, JAPAN" became "JAPAN". And the subset rule let a country alone match any city in
it, so "TOKYO, JAPAN" matched "NAGOYA, JAPAN" and "VIETNAM" matched "HO CHI MINH, VIETNAM".
Now a subset matches only when the extra words are a country, and a code is never deleted
if that would leave only a country or nothing.
"""
from __future__ import annotations

import pytest

from backend.compare.comparator import compare_single_field

PORT = "port_of_discharge"


@pytest.mark.parametrize(("si", "bl"), [
    ("PORT KLANG, MALAYSIA", "PORT DICKSON, MALAYSIA"),
    ("MANILA NORTH HARBOUR", "MANILA SOUTH HARBOUR"),
    ("MOMBASA, KENYA (KEMBA)", "TUTICORIN, INDIA (KEMBA)"),
    ("TOKYO, JAPAN", "NAGOYA, JAPAN"),
    ("PERTH, AUSTRALIA", "SYDNEY, AUSTRALIA"),
    ("HO CHI MINH, VIETNAM", "VIETNAM"),
    ("CHINA", "SHANGHAI, CHINA"),
    ("TOKYO", "OSAKA"),
])
def test_different_ports_are_a_mismatch(si: str, bl: str) -> None:
    assert compare_single_field(PORT, si, bl) == "mismatch"


@pytest.mark.parametrize(("si", "bl"), [
    ("PORT KLANG (MYPKG)", "PORT KLANG"),
    ("BUSAN", "BUSAN, SOUTH KOREA"),
    ("MYPKG PORT KLANG", "PORT KLANG"),
    ("NHAVA SHEVA, INDIA", "nhava sheva, india"),
    ("PORT KLANG, MALAYSIA (MYPKG)", "PORT KLANG MYPKG"),
    ("SHANGHAI, CHINA", "CNSHA SHANGHAI"),
    ("MYPKG PORT KLANG", "PORT KLANG, MALAYSIA"),
    ("TOKYO", "TOKYO, JAPAN"),
    ("PERTH", "PERTH, AUSTRALIA"),
    ("SHANGHAI, CHINA", "CHINA, SHANGHAI"),
    ("SINGAPORE", "SINGAPORE (SGSIN)"),
    ("JEBEL ALI", "JEBEL ALI, UAE"),
    ("SHANGHAI, CN", "SHANGHAI (CNSHA)"),
])
def test_the_same_port_written_differently_is_a_match(si: str, bl: str) -> None:
    assert compare_single_field(PORT, si, bl) == "match"


def test_every_saved_port_verdict_is_unchanged() -> None:
    """The fix only closes the holes above: every saved port verdict stays the same."""
    import json
    from pathlib import Path

    src = (Path(__file__).resolve().parents[1] / "frontend" / "results.js").read_text(encoding="utf-8")
    rows = [r for e in json.loads(src[src.index("["): src.rindex("]") + 1]) for r in e.get("rows", [])
            if r["field"] in ("port_of_loading", "port_of_discharge")]

    assert len(rows) == 228   # 114 compared emails, two ports each
    changed = [(r["si_norm"], r["bl_norm"], r["verdict"]) for r in rows
               if compare_single_field(r["field"], r["si_norm"], r["bl_norm"]) != r["verdict"]]
    assert changed == []
