"""Real Qwen, one request. Skipped when QWEN_API_KEY is not set."""
from __future__ import annotations

import os

import pytest

from extract_ai import AiExtractor
from qwen_model import qwen_model
from test_extract_ai_live import PAIRS

pytestmark = pytest.mark.skipif(not os.environ.get("QWEN_API_KEY"), reason="no QWEN_API_KEY")


def test_qwen_reads_the_pairs_from_an_excel_si() -> None:
    fields = AiExtractor(qwen_model).extract_fields("email_055", PAIRS)

    assert fields is not None
    assert fields["port_of_loading"]["label_seen"] == "Load Port"
    assert fields["port_of_loading"]["raw"] == "SINGAPORE"
    assert fields["consignee"]["raw"] == "AL GURG STATIONERY LLC"
    assert fields["container_count"]["raw"] == "12 x 20'FCL"
    assert fields["gross_weight_kg"]["raw"] == "243588"


def test_port_keeps_only_the_port_when_the_reader_glued_the_next_row_on() -> None:
    pairs = [("Shipper", "APRIL FAR EAST (M) SDN BHD"), ("POL", "PORT KLANG (WESTPORT), MALAYSIA"),
             ("POD", "NEW YORK, US | Export Carrier (vessel, voyage) | VISION 202 V.002"),
             ("No. of Containers", "5 x 20'FCL")]

    fields = AiExtractor(qwen_model).extract_fields("email_411", pairs)

    assert fields is not None
    assert fields["port_of_discharge"]["raw"] == "NEW YORK, US"
