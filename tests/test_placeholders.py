"""A placeholder is a missing value, whichever way it is written (#147 A3).

"TBA.", "T.B.A", "TO BE ADVISED" and "N.A." compared as real values, so a blank
field came out a mismatch rather than the missing value that outranks one.
"""
from __future__ import annotations

import pytest

from backend.app import apply_cleaner
from backend.compare.comparator import compare_single_field
from backend.contracts import FIELD_NAMES


def norm(field: str, raw: str) -> str | None:
    fields = {name: {"present": False, "raw": None, "label_seen": None} for name in FIELD_NAMES}
    fields[field] = {"present": True, "raw": raw, "label_seen": field}

    return apply_cleaner(fields)[field]["norm"]


@pytest.mark.parametrize("raw", ["TBA", "TBA.", "T.B.A", "t.b.c.", "TO BE ADVISED", "N/A", "N.A.", "TBA x 40HC"])
def test_a_placeholder_is_missing_not_a_mismatch(raw: str) -> None:
    field = "container_count" if "40HC" in raw else "consignee"

    assert compare_single_field(field, norm(field, raw), norm(field, "BETA TRADING")) == "missing"


@pytest.mark.parametrize("raw", ["TBC LOGISTICS SDN BHD", "NILE SHIPPING", "NAGOYA", "TBILISI", "NONE", "NIL"])
def test_a_real_value_that_starts_like_one_is_kept(raw: str) -> None:
    assert norm("consignee", raw) is not None


def test_notify_party_none_on_both_documents_is_a_match() -> None:
    field = "notify_party"

    assert compare_single_field(field, norm(field, "NONE"), norm(field, "NONE")) == "match"
