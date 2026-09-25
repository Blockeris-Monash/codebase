"""Two different ports never compare as the same port (#147 A3).

The comparator deleted every bare five-letter word as if it were a UN/LOCODE, then
counted any subset of the remaining words as a match. KLANG, NORTH, SOUTH and CHINA
are all five letters, so PORT KLANG matched PORT DICKSON. The dataset never showed it
because no planted defect changes one word of a two-word port.
"""
from __future__ import annotations

import pytest

from backend.compare.comparator import compare_single_field

PORT = "port_of_discharge"


@pytest.mark.parametrize(("si", "bl"), [
    ("PORT KLANG, MALAYSIA", "PORT DICKSON, MALAYSIA"),
    ("MANILA NORTH HARBOUR", "MANILA SOUTH HARBOUR"),
    ("MOMBASA, KENYA (KEMBA)", "TUTICORIN, INDIA (KEMBA)"),
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
])
def test_the_same_port_written_differently_is_a_match(si: str, bl: str) -> None:
    assert compare_single_field(PORT, si, bl) == "match"
