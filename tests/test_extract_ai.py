"""The AI extractor returns the same DocumentExtract as the rule-based one,
for every format Lane A can read."""
from __future__ import annotations

from pathlib import Path

import pytest

from contract_types import Attachment, FIELD_NAMES
from extract_ai import AiExtractor
from make_fixtures import attachment_meta


def canned_model(text: str) -> dict[str, dict[str, object]]:
    """Stand-in for Gemini: every field found, values copied from email_055_SI."""
    values = {
        "shipper": ("Shipper/Exporter", "APRIL FINE PAPER TRADING"),
        "consignee": ("Consignee (Non-Negotiable)", "AL GURG STATIONERY LLC"),
        "notify_party": ("NOTIFY PARTY", "AL GURG STATIONERY LLC"),
        "port_of_loading": ("Load Port", "SINGAPORE"),
        "port_of_discharge": ("POD", "KARACHI, PAKISTAN"),
        "container_count": ("Container Count", "12 x 20'FCL"),
        "gross_weight_kg": ("GROSS WEIGHT", "243588"),
    }
    return {name: {"present": True, "label_seen": label, "raw": raw}
            for name, (label, raw) in values.items()}


def test_excel_si_is_read_then_extracted(data_dir: Path) -> None:
    seen: list[str] = []

    def spying_model(text: str) -> dict[str, dict[str, object]]:
        seen.append(text)
        return canned_model(text)

    meta: Attachment = attachment_meta("attachments/email_055_SI.xlsx")
    result = AiExtractor(spying_model).document_extract(str(data_dir), "email_055", meta)

    assert result["format"] == "xlsx"
    assert result["parse_status"] == "ok"
    assert result["detected_doc_type"] == "SI"
    assert set(result["fields"]) == set(FIELD_NAMES)
    assert result["fields"]["gross_weight_kg"]["raw"] == "243588"
    assert "Load Port: SINGAPORE" in seen[0]


def excel_si_meta() -> Attachment:
    return attachment_meta("attachments/email_055_SI.xlsx")


def test_model_failure_is_retried_then_reported_unreadable(
        data_dir: Path, caplog: pytest.LogCaptureFixture) -> None:
    calls: list[str] = []

    def broken_model(text: str) -> dict[str, dict[str, object]]:
        calls.append(text)
        raise RuntimeError("429 RESOURCE_EXHAUSTED")

    result = AiExtractor(broken_model, wait=0).document_extract(
        str(data_dir), "email_055", excel_si_meta())

    assert len(calls) == 3
    assert result["parse_status"] == "unreadable"
    assert result["detected_doc_type"] == "SI"
    assert not any(f["present"] for f in result["fields"].values())
    assert "email_055" in caplog.text and "429 RESOURCE_EXHAUSTED" in caplog.text


def test_a_temporary_failure_recovers(data_dir: Path) -> None:
    calls: list[str] = []

    def flaky_model(text: str) -> dict[str, dict[str, object]]:
        calls.append(text)
        if len(calls) < 3:
            raise RuntimeError("503 UNAVAILABLE")
        return canned_model(text)

    result = AiExtractor(flaky_model, wait=0).document_extract(
        str(data_dir), "email_055", excel_si_meta())

    assert result["parse_status"] == "ok"
    assert result["fields"]["port_of_loading"]["raw"] == "SINGAPORE"


def test_a_value_not_in_the_document_is_rejected(
        data_dir: Path, caplog: pytest.LogCaptureFixture) -> None:
    def inventing_model(text: str) -> dict[str, dict[str, object]]:
        fields = canned_model(text)
        fields["port_of_discharge"] = {"present": True, "label_seen": "POD", "raw": "BUSAN"}
        return fields

    result = AiExtractor(inventing_model).document_extract(
        str(data_dir), "email_055", excel_si_meta())

    assert result["fields"]["port_of_discharge"] == {
        "present": False, "label_seen": None, "raw": None}
    assert result["fields"]["port_of_loading"]["present"] is True
    assert "port_of_discharge" in caplog.text


def test_a_value_differing_only_in_spacing_is_accepted(data_dir: Path) -> None:
    def spaced_model(text: str) -> dict[str, dict[str, object]]:
        fields = canned_model(text)
        fields["port_of_discharge"] = {"present": True, "label_seen": "POD",
                                       "raw": "KARACHI,   PAKISTAN"}
        return fields

    result = AiExtractor(spaced_model).document_extract(
        str(data_dir), "email_055", excel_si_meta())

    assert result["fields"]["port_of_discharge"]["present"] is True
