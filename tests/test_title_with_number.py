"""A document whose title line also carries its number is still recognised (#147 B3).

"BL INSTRUCTION: 3043223023" and "BILL OF LADING NO. SIJ6060148" were read as some other
document, so a correct SI and BL pair went to a person as wrong_doc_type. Found when the
three pairs of the team's own timing test were put through Upload files: all three came
back wrong_doc_type instead of match / consignee / weight and notify party.
"""
from __future__ import annotations

import pytest

from backend.read.labels import detect_doc_type


@pytest.mark.parametrize(("title", "role"), [
    ("BL INSTRUCTION: 3043223023", "SI"),
    ("BILL OF LADING: 3043223023", "BL"),
    ("BILL OF LADING NO. SIJ6060148", "BL"),
    ("SHIPPING INSTRUCTION", "SI"),
    ("BILL OF LADING (DRAFT)", "BL"),
])
def test_the_title_is_read_past_its_number(title: str, role: str) -> None:
    assert detect_doc_type(title) == role


@pytest.mark.parametrize("title", ["PACKING LIST", "COMMERCIAL INVOICE: 123", "Shipper: APRIL FINE PAPER"])
def test_another_document_is_still_named_as_itself(title: str) -> None:
    assert detect_doc_type(title) not in {"SI", "BL"}
