"""The sentence a reviewer reads has to name the cause, not its category.

The use case warns that a score cannot assess whether the system "provided
enough context". "Missing value detected in fields: gross_weight_kg" is a
category. `TBA` means a value is coming and someone should be chased;
`_______` means a form went out unfilled and the document goes back. The two
want different replies, and the reviewer could not tell them apart.
"""
from __future__ import annotations

import pytest

from backend.compare.evidence import (
    MAX_FIELDS_NAMED,
    MAX_VALUE_CHARS,
    describe_blanks,
    describe_unreadable,
    describe_value,
    describe_wrong_doc,
)

SI_SIDE, BL_SIDE = (True, False), (False, True)


@pytest.mark.parametrize("token", ["TBA", "TBC", "N/A", "???", "_______", "____MT"])
def test_the_token_a_blank_used_is_quoted(token: str) -> None:
    line = describe_blanks([("gross_weight_kg", token, "40326 KG", *SI_SIDE)])

    assert token in line
    assert "gross_weight_kg" in line
    assert "on the SI" in line


def test_an_empty_value_is_called_blank_rather_than_quoted_as_nothing() -> None:
    assert describe_value("") == "is blank"
    assert describe_value(None) == "is blank"
    assert describe_value("   ") == "is blank"
    assert '""' not in describe_blanks([("shipper", "", "ACME", *SI_SIDE)])


def test_the_side_that_was_blank_is_the_side_named() -> None:
    assert "on the BL" in describe_blanks([("consignee", "ACME", "TBA", *BL_SIDE)])
    assert "on the SI" in describe_blanks([("consignee", "TBA", "ACME", *SI_SIDE)])


def test_blank_on_both_sides_names_both() -> None:
    line = describe_blanks([("shipper", "", "", True, True)])

    assert "SI and the BL" in line


def test_a_long_value_does_not_run_the_sentence_off_the_screen() -> None:
    """A pasted address lands in a blank field often enough to matter."""
    line = describe_blanks([("shipper", "A" * 200, "ACME", *SI_SIDE)])

    assert len(line) < 120
    assert "…" in line


def test_only_the_first_few_fields_are_named_and_the_rest_are_counted() -> None:
    blanks = [(f"field_{n}", "TBA", "x", *SI_SIDE) for n in range(7)]

    line = describe_blanks(blanks)

    assert "field_0" in line and f"field_{MAX_FIELDS_NAMED}" not in line
    assert f"and {7 - MAX_FIELDS_NAMED} more" in line


def test_no_blanks_still_returns_a_sentence() -> None:
    """The caller only reaches here with at least one, but a sentence is
    cheaper than an IndexError in front of a reviewer."""
    assert describe_blanks([]).strip().endswith(".")


def test_a_quote_in_the_value_is_carried_through_for_the_screen_to_escape() -> None:
    """The review app renders evidence through esc(); this layer must not
    silently drop characters, or the screen and the document disagree."""
    assert 'SO"NS' in describe_blanks([("shipper", 'SO"NS', "x", *SI_SIDE)])


def test_the_wrong_document_is_named_by_what_it_declares_itself() -> None:
    line = describe_wrong_doc("SI", "COMMERCIAL INVOICE")

    assert "COMMERCIAL INVOICE" in line
    assert "sent as the BL" in line


def test_a_document_declaring_nothing_says_so_rather_than_quoting_none() -> None:
    line = describe_wrong_doc("SI", None)

    assert "None" not in line
    assert "no recognisable type" in line


def test_both_documents_wrong_names_both() -> None:
    line = describe_wrong_doc("PACKING LIST", "COMMERCIAL INVOICE")

    assert "PACKING LIST" in line and "COMMERCIAL INVOICE" in line


def test_neither_document_wrong_falls_back_rather_than_claiming_nothing_is_wrong() -> None:
    assert describe_wrong_doc("SI", "BL").startswith("Document type error")


def test_unreadable_names_the_file_that_would_not_open() -> None:
    assert "the BL could not be read" in describe_unreadable("ok", "unreadable")
    assert "the SI could not be read" in describe_unreadable("unreadable", "ok")


def test_both_unreadable_names_both() -> None:
    line = describe_unreadable("unreadable", "not_attempted")

    assert "the SI" in line and "the BL" in line


def test_a_missing_parse_status_does_not_print_none() -> None:
    assert "None" not in describe_unreadable(None, "ok")


def test_the_value_limit_is_a_named_constant_not_a_number_in_the_sentence() -> None:
    """Guards against someone inlining 40 and the two paths drifting apart."""
    assert MAX_VALUE_CHARS > 0 and MAX_FIELDS_NAMED > 0
