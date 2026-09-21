"""The AI extractor turns Lane A's label/value pairs into the seven fields.

It does not read files, check the document type or set parse_status. Those are
Lane A's result, so every test here hands it pairs directly."""
from __future__ import annotations

import pytest

from backend.contracts import ExtractedField
from backend.extract.ai import AiExtractor

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


def canned_model(text: str) -> dict[str, ExtractedField]:
    """Stand-in for Gemini: every field found, values copied from PAIRS."""
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


def test_the_model_receives_the_pairs_as_label_value_lines() -> None:
    seen: list[str] = []

    def spying_model(text: str) -> dict[str, ExtractedField]:
        seen.append(text)
        return canned_model(text)

    fields = AiExtractor(spying_model).extract_fields("email_055", PAIRS)

    assert fields is not None
    assert "Load Port: SINGAPORE" in seen[0]
    assert fields["gross_weight_kg"]["raw"] == "243588"
    assert len(fields) == 7


def test_model_failure_is_retried_then_reported_as_no_answer(
        caplog: pytest.LogCaptureFixture) -> None:
    calls: list[str] = []

    def broken_model(text: str) -> dict[str, ExtractedField]:
        calls.append(text)
        raise RuntimeError("429 RESOURCE_EXHAUSTED")

    fields = AiExtractor(broken_model, wait=0).extract_fields("email_055", PAIRS)

    assert fields is None
    assert len(calls) == 3
    assert "email_055" in caplog.text and "429 RESOURCE_EXHAUSTED" in caplog.text


def test_a_temporary_failure_recovers() -> None:
    calls: list[str] = []

    def flaky_model(text: str) -> dict[str, ExtractedField]:
        calls.append(text)
        if len(calls) < 3:
            raise RuntimeError("503 UNAVAILABLE")
        return canned_model(text)

    fields = AiExtractor(flaky_model, wait=0).extract_fields("email_055", PAIRS)

    assert fields is not None
    assert fields["port_of_loading"]["raw"] == "SINGAPORE"


def test_a_value_not_in_the_document_is_rejected(
        caplog: pytest.LogCaptureFixture) -> None:
    def inventing_model(text: str) -> dict[str, ExtractedField]:
        fields = canned_model(text)
        fields["port_of_discharge"] = {"present": True, "label_seen": "POD", "raw": "BUSAN"}
        return fields

    fields = AiExtractor(inventing_model).extract_fields("email_055", PAIRS)

    assert fields is not None
    assert fields["port_of_discharge"] == {"present": False, "label_seen": None, "raw": None}
    assert fields["port_of_loading"]["present"] is True
    assert "port_of_discharge" in caplog.text


def test_a_value_differing_only_in_spacing_is_accepted() -> None:
    def spaced_model(text: str) -> dict[str, ExtractedField]:
        fields = canned_model(text)
        fields["port_of_discharge"] = {"present": True, "label_seen": "POD",
                                       "raw": "KARACHI,   PAKISTAN"}
        return fields

    fields = AiExtractor(spaced_model).extract_fields("email_055", PAIRS)

    assert fields is not None
    assert fields["port_of_discharge"]["present"] is True


def test_prompt_tells_the_model_to_stop_a_port_at_the_first_segment() -> None:
    from backend.extract.gemini import PROMPT

    # Lane A's PDF reader sometimes glues the next row (vessel, voyage) onto a port cell.
    assert 'For a party or a port, keep only the name, the first segment before any " | "' in PROMPT
