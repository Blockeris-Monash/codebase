"""X12 EDI 304 — the format real shipping runs on, none of it in the dataset.

Tested against a real published carrier specification rather than a sample
we invented. See tests/samples/Edi304Sample.edi.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from contract_types import FIELD_NAMES
from labels import canonical_field
from read_documents import READERS, document_title, read_document
from read_edi import delimiters, element, gross_weight_kg, ports, segments

SAMPLE = Path(__file__).resolve().parent / "samples" / "Edi304Sample.edi"


def sample_fields() -> dict[str, str]:
    _, pairs = read_document(SAMPLE)
    return {canonical_field(label): value for label, value in pairs
            if canonical_field(label)}


def test_edi_reaches_all_seven_fields() -> None:
    """The whole point: a completely different input format lands on the
    same seven fields, so nothing downstream changes."""
    assert sorted(sample_fields()) == sorted(FIELD_NAMES)


def test_edi_goes_through_the_same_dispatch() -> None:
    """No special case anywhere - it is one more entry in READERS."""
    status, pairs = read_document(SAMPLE)

    assert status == "ok"
    assert len(pairs) == len(FIELD_NAMES)


def test_a_304_declares_itself_a_shipping_instruction() -> None:
    """EDI has no title line; the ST segment carries the transaction code."""
    assert document_title(SAMPLE) == "SHIPPING INSTRUCTION"


def test_edi_is_in_the_reader_table() -> None:
    assert "edi" in READERS


# --- the quirks the format brings with it -------------------------------

def test_the_port_is_the_code_not_the_city() -> None:
    """Inverts the document rule. On paper the UN/LOCODE is a decoy and the
    city name is authoritative, because that is how the defects were
    planted. In EDI the code is all there is."""
    assert sample_fields()["port_of_loading"] == "CNSZX"


@pytest.mark.parametrize("qualifier,label", [("L", "Port of Loading"),
                                             ("D", "Port of Discharge")])
def test_port_qualifier_selects_the_field(qualifier: str, label: str) -> None:
    found = ports([["R4", qualifier, "UN", "SGSIN"]])

    assert found == [(label, "SGSIN")]


def test_gross_weight_sums_the_lading_lines() -> None:
    """A 304 carries one L0 per lading line, not one total."""
    lading = [["L0", "1", "", "", "8384", "G", "", "", "", "", "", "K"],
              ["L0", "2", "", "", "8384", "G", "", "", "", "", "", "K"]]

    assert gross_weight_kg(lading) == [("Gross Weight (KG)", "16,768 KG")]


def test_net_weight_lines_are_not_counted_as_gross() -> None:
    """Element 5 is the weight qualifier. N is net, and netting it into the
    gross total would understate the shipment."""
    lading = [["L0", "1", "", "", "8384", "G", "", "", "", "", "", "K"],
              ["L0", "2", "", "", "1000", "N", "", "", "", "", "", "K"]]

    assert gross_weight_kg(lading) == [("Gross Weight (KG)", "8,384 KG")]


def test_pounds_are_converted_to_kilograms() -> None:
    """Element 11 is the unit. L is pounds, and the field we compare is kg."""
    lading = [["L0", "1", "", "", "2205", "G", "", "", "", "", "", "L"]]

    assert gross_weight_kg(lading) == [("Gross Weight (KG)", "1,000 KG")]


def test_omitted_trailing_elements_do_not_raise() -> None:
    """Segments are routinely cut short once the rest would be empty."""
    assert element(["R4", "L"], 11) == ""


def test_comments_and_line_breaks_are_ignored() -> None:
    """A real interchange is often one long line; ours is split for reading,
    with a provenance header on top."""
    parsed = segments("# a comment\nISA*00*x~\nST*304*0001~")

    assert parsed == [["ISA", "00", "x"], ["ST", "304", "0001"]]


# --- X12 declares its own punctuation ----------------------------------

PIPE_ISA = ("ISA|00|          |00|          |ZZ|SENDER         |ZZ|RECEIVER"
            "       |200410|1328|U|00401|000003055|0|T|>\nN1|SF|ACME LTD\n")
STAR_ISA = "ISA*00*x*ZZ*S*ZZ*R*200410*1328*U*00401*1*0*T*>~N1*SF*ACME LTD~"


@pytest.mark.parametrize("text,expected", [
    (STAR_ISA, ("*", "~")),
    (PIPE_ISA, ("|", "\n")),
])
def test_delimiters_come_from_the_isa_not_from_us(text: str, expected: tuple) -> None:
    """X12 does not fix its punctuation. The ISA's fourth character IS the
    element separator and the terminator follows the fixed-width header.
    Hardcoding "*" and "~" works until a partner sends "|"."""
    assert delimiters(text) == expected


@pytest.mark.parametrize("text", [STAR_ISA, PIPE_ISA])
def test_the_same_data_parses_under_either_delimiter(text: str) -> None:
    parsed = segments(text)

    assert ["N1", "SF", "ACME LTD"] in parsed


def test_delimiters_fall_back_when_the_header_is_malformed() -> None:
    """Padding is sometimes lost in transit, so the fixed-width offset can
    miss. Falling back beats raising."""
    assert delimiters("not an interchange at all") == ("*", "~")
