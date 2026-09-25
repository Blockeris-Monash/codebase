"""Qwen adapter: the network call is faked, so these run offline."""
from __future__ import annotations

import json

import pytest

from backend.extract import qwen as qm

FIELDS = ("shipper", "consignee", "notify_party", "port_of_loading",
          "port_of_discharge", "container_count", "gross_weight_kg")


@pytest.fixture(autouse=True)
def fake_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("QWEN_API_KEY", "test-key")


def reply_for(**overrides: dict) -> dict:
    fields = {name: {"present": True, "label_seen": name, "raw": "X"} for name in FIELDS}
    fields.update(overrides)
    return {"content": [{"type": "text", "text": json.dumps(fields)}]}


def test_returns_the_seven_fields_as_plain_dicts() -> None:
    fields = qm.qwen_model("Load Port: SINGAPORE", post=lambda url, headers, body: reply_for(
        port_of_loading={"present": True, "label_seen": "Load Port", "raw": "SINGAPORE"}))

    assert set(fields) == set(FIELDS)
    assert fields["port_of_loading"] == {"present": True, "label_seen": "Load Port", "raw": "SINGAPORE"}


def test_reads_json_wrapped_in_fences_and_blank_lines() -> None:
    wrapped = {"content": [{"type": "text",
                            "text": "\n\n```json\n" + reply_for()["content"][0]["text"] + "\n```\n"}]}

    assert set(qm.qwen_model("doc", post=lambda url, headers, body: wrapped)) == set(FIELDS)


def test_sends_key_user_agent_and_the_document(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("QWEN_API_KEY", "secret-key")
    monkeypatch.setenv("QWEN_BASE_URL", "https://example.test/")
    seen: dict = {}

    def post(url: str, headers: dict, body: dict) -> dict:
        seen.update(url=url, headers=headers, body=body)
        return reply_for()

    qm.qwen_model("Load Port: SINGAPORE", post=post)

    assert seen["url"] == "https://example.test/v1/messages"
    assert seen["headers"]["x-api-key"] == "secret-key"
    assert seen["headers"]["user-agent"]  # the gateway blocks requests without one
    assert "Load Port: SINGAPORE" in seen["body"]["messages"][0]["content"]
    assert seen["body"]["model"]
    # Qwen thinks before it answers and that counts against the limit (about 900 used of 1024 before).
    assert seen["body"]["max_tokens"] >= 4096


def test_a_reply_that_is_not_the_seven_fields_raises() -> None:
    bad = {"content": [{"type": "text", "text": json.dumps({"shipper": {"present": True}})}]}

    with pytest.raises(ValueError):
        qm.qwen_model("doc", post=lambda url, headers, body: bad)


def test_missing_key_is_a_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("QWEN_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="QWEN_API_KEY"):
        qm.qwen_model("doc", post=lambda url, headers, body: reply_for())


class FakeResponse:
    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def read(self) -> bytes:
        return b"{}"


def timeout_used(monkeypatch: pytest.MonkeyPatch) -> float:
    seen: list[float] = []

    def fake_urlopen(request: object, timeout: float) -> FakeResponse:
        seen.append(timeout)
        return FakeResponse()

    monkeypatch.setattr(qm.urllib.request, "urlopen", fake_urlopen)
    qm.http_post("https://example.test/v1/messages", {}, {})
    return seen[0]


def test_one_call_waits_15_seconds_at_most(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("QWEN_TIMEOUT_SECONDS", raising=False)

    assert timeout_used(monkeypatch) == 15


def test_the_wait_per_call_can_be_set_in_the_environment(
        monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("QWEN_TIMEOUT_SECONDS", "40")

    assert timeout_used(monkeypatch) == 40
