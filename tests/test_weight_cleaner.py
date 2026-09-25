"""The live weight cleaner reads the number written against its unit (#147 A3).

clean_weight joined every digit in the value, so "2 x 20GP 40,326 KG" became 22,040,326 kg,
and any "MT" anywhere - a "NET: ___ MTS" decoy beside the gross weight - multiplied the lot
by 1000. The label's own unit was dropped too, so 40,326 under "Gross Weight (LBS)" was
compared as 40,326 kg. Nothing tested this cleaner: the tests exercised the reference one.
"""
from __future__ import annotations

import pytest

from backend.app import apply_cleaner, clean_weight
from backend.compare.comparator import compare_single_field
from backend.contracts import FIELD_NAMES

WEIGHT = "gross_weight_kg"


@pytest.mark.parametrize(("raw", "kilograms"), [
    ("2 x 20GP 40,326 KG", 40326.0),
    ("40,326 KG (NET: ___ MTS)", 40326.0),
    ("12,500 KGS (12.5 MT)", 12500.0),
    ("24000 KG (EXCL. PALLETS: 2 PCS)", 24000.0),
    ("12.5 MT", 12500.0),
    ("40,176", 40176.0),
    ("40326.5 KGS", 40326.5),
    ("NET 38,000 KG GROSS 40,326 KG", 40326.0),
    ("40.326,000 KG", 40.326),  # decimal comma: still misread (xfail edge_b3c), but never as 326,000
])
def test_the_weight_is_the_number_written_against_its_unit(raw: str, kilograms: float) -> None:
    assert float(clean_weight(raw)) == kilograms


def test_pounds_are_converted_not_read_as_kilograms() -> None:
    assert float(clean_weight("88,904 LBS")) == pytest.approx(40326.2, abs=0.1)


def test_a_value_with_no_number_is_blank() -> None:
    assert clean_weight("TBA") == ""


def weight_row(raw: str, label: str) -> dict:
    fields = {name: {"present": False, "raw": None, "label_seen": None} for name in FIELD_NAMES}
    fields[WEIGHT] = {"present": True, "raw": raw, "label_seen": label}

    return apply_cleaner(fields)[WEIGHT]


def test_a_unit_in_the_label_applies_to_a_bare_number() -> None:
    si = weight_row("40,326", "Gross Weight (LBS)")
    bl = weight_row("40,326 KG", "Gross Weight")

    assert compare_single_field(WEIGHT, si["norm"], bl["norm"]) == "mismatch"


def test_a_unit_in_the_value_wins_over_the_label() -> None:
    assert float(weight_row("40,326 KG", "Gross Weight (LBS)")["norm"]) == 40326.0
