"""A second model behind the first: when Qwen fails or hangs, Gemini answers.

The models are fakes, so these run offline and fast."""
from __future__ import annotations

import time

import pytest

from backend.contracts import ExtractedField
from backend.extract.ai import AiExtractor
from backend.extract.fallback import with_fallback

FIELDS = ("shipper", "consignee", "notify_party", "port_of_loading",
          "port_of_discharge", "container_count", "gross_weight_kg")


def answer(tag: str) -> dict[str, ExtractedField]:
    return {name: {"present": True, "label_seen": name, "raw": tag} for name in FIELDS}


def broken(text: str) -> dict[str, ExtractedField]:
    raise RuntimeError("gateway unreachable")


def test_uses_the_first_model_when_it_works_and_never_calls_the_second() -> None:
    calls: list[str] = []

    def second(text: str) -> dict[str, ExtractedField]:
        calls.append(text)
        return answer("second")

    model = with_fallback(lambda text: answer("first"), second)

    assert model("doc")["shipper"]["raw"] == "first" and calls == []


def test_falls_back_to_the_second_model_when_the_first_fails() -> None:
    model = with_fallback(broken, lambda text: answer("second"))

    assert model("doc")["shipper"]["raw"] == "second"


def test_falls_back_when_the_first_model_hangs_past_the_timeout() -> None:
    def slow(text: str) -> dict[str, ExtractedField]:
        time.sleep(2)
        return answer("first")

    model = with_fallback(slow, lambda text: answer("second"), first_timeout=0.2)

    started = time.perf_counter()
    result = model("doc")

    assert result["shipper"]["raw"] == "second"
    assert time.perf_counter() - started < 1.5  # did not wait for the slow model


def test_raises_when_both_models_fail() -> None:
    model = with_fallback(broken, broken)

    with pytest.raises(RuntimeError, match="gateway unreachable"):
        model("doc")


def test_the_extractor_gets_its_fields_from_the_second_model_when_the_first_is_down() -> None:
    pairs = [("Shipper", "ACME TRADING")] + [(name, "ACME TRADING") for name in FIELDS[1:]]
    second = lambda text: {name: {"present": True, "label_seen": "Shipper", "raw": "ACME TRADING"} for name in FIELDS}
    extractor = AiExtractor(with_fallback(broken, second), tries=1, wait=0)

    fields = extractor.extract_fields("email_001", pairs)

    assert fields is not None and fields["shipper"]["raw"] == "ACME TRADING"
