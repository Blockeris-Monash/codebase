"""A value the model returns must appear whole, under the label it says it read (#147 A3).

The guard was a substring test on the whole document, so three wrong readings passed:
the shipper's name returned as the consignee, "100" or "12" taken from "12,100", and "1"
from "Packages: 1 lot". On documents whose labels the rules do not know, any of them could
turn into a false match. The last one still passes: "Packages" is a label the rules do not
know, and "1" is whole under it, so only the meaning is wrong - that needs a person.
"""
from __future__ import annotations

import pytest

from backend.contracts import FIELD_NAMES
from backend.extract.ai import AiExtractor

PAIRS = [("Shipper", "ACME LTD"), ("Consignee", "BETA TRADING"), ("Notify Party", "BETA TRADING"),
         ("Port of Loading", "PORT KLANG"), ("Port of Discharge", "JEBEL ALI"),
         ("Gross Weight", "12,100 KG"), ("Packages", "1 lot"), ("Containers", "2 x 40HC")]


def extracted(field: str, label: str, raw: str) -> dict:
    """What a model might return: every field absent except the one under test."""
    fields = {name: {"present": False, "label_seen": None, "raw": None} for name in FIELD_NAMES}
    fields[field] = {"present": True, "label_seen": label, "raw": raw}
    extractor = AiExtractor(lambda text: fields, tries=1)

    return extractor.extract_fields("email_001", PAIRS)[field]


@pytest.mark.parametrize(("field", "label", "raw"), [
    ("consignee", "Consignee", "ACME LTD"),
    ("consignee", "Shipper", "ACME LTD"),
    ("gross_weight_kg", "Gross Weight", "100"),
    ("gross_weight_kg", "Gross Weight", "12"),
])
def test_a_value_not_whole_under_its_label_is_rejected(field: str, label: str, raw: str) -> None:
    assert extracted(field, label, raw)["present"] is False


@pytest.mark.parametrize(("field", "label", "raw"), [
    ("consignee", "Consignee", "BETA TRADING"),
    ("gross_weight_kg", "Gross Weight", "12,100 KG"),
    ("container_count", "Containers", "2 x 40HC"),
    ("port_of_loading", "Port of Loading", "PORT  KLANG"),
])
def test_a_value_read_from_its_own_label_is_kept(field: str, label: str, raw: str) -> None:
    assert extracted(field, label, raw)["present"] is True
