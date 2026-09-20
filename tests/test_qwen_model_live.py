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
