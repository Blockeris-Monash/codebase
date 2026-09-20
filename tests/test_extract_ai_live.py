"""Real Gemini, one request. Skipped when no API key is set."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from extract_ai import AiExtractor
from gemini_model import gemini_model
from make_fixtures import attachment_meta

pytestmark = pytest.mark.skipif(
    not (os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")),
    reason="no GOOGLE_API_KEY")


def test_gemini_reads_the_excel_si(data_dir: Path) -> None:
    meta = attachment_meta("attachments/email_055_SI.xlsx")
    result = AiExtractor(gemini_model).document_extract(str(data_dir), "email_055", meta)

    assert result["parse_status"] == "ok"
    assert result["fields"]["port_of_loading"]["label_seen"] == "Load Port"
    assert result["fields"]["port_of_loading"]["raw"] == "SINGAPORE"
    assert result["fields"]["container_count"]["raw"] == "12 x 20'FCL"
    assert result["fields"]["gross_weight_kg"]["raw"] == "243588"
