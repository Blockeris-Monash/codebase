"""Real Gemini, one request. Skipped when no API key is set."""
from __future__ import annotations

import os

import pytest

from backend.extract.ai import AiExtractor
from backend.extract.gemini import gemini_model

pytestmark = pytest.mark.skipif(
    not (os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")),
    reason="no GOOGLE_API_KEY")

# Pairs as Lane A's reader returns them for email_055_SI.xlsx.
PAIRS = [
    ("BL INSTRUCTION", "3658202970"),
    ("Shipper/Exporter", "APRIL FINE PAPER TRADING | ON BEHALF OF VITAL SOLUTIONS PTE LTD"),
    ("Consignee (Non-Negotiable)", "AL GURG STATIONERY LLC | P.O. BOX 5069"),
    ("NOTIFY PARTY", "AL GURG STATIONERY LLC | P.O. BOX 5069"),
    ("Load Port", "SINGAPORE"),
    ("POD", "KARACHI, PAKISTAN"),
    ("Container Count", "12 x 20'FCL"),
    ("GROSS WEIGHT", "243588"),
    ("Export Carrier (vessel, voyage)", "PACIFIC SUN 1 V.251073E"),
]


def test_gemini_reads_the_pairs_from_an_excel_si() -> None:
    fields = AiExtractor(gemini_model).extract_fields("email_055", PAIRS)

    assert fields is not None
    assert fields["port_of_loading"]["label_seen"] == "Load Port"
    assert fields["port_of_loading"]["raw"] == "SINGAPORE"
    assert fields["consignee"]["raw"] == "AL GURG STATIONERY LLC"
    assert fields["container_count"]["raw"] == "12 x 20'FCL"
    assert fields["gross_weight_kg"]["raw"] == "243588"
