"""Gemini is the backup when Qwen is slow, so it must not be slow without end either.

The client is faked, so these run offline."""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from google import genai

from backend import reply
from backend.extract import gemini, vision

FIELDS = ("shipper", "consignee", "notify_party", "port_of_loading",
          "port_of_discharge", "container_count", "gross_weight_kg")


@pytest.fixture
def clients(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    """The keyword arguments of every genai.Client built."""
    built: list[dict] = []
    reply = json.dumps({name: {"present": False, "label_seen": None, "raw": None}
                        for name in FIELDS})

    class FakeModels:
        def generate_content(self, **kwargs: object) -> SimpleNamespace:
            return SimpleNamespace(text=reply, parsed=gemini.ModelFields.model_validate_json(reply))

    class FakeClient:
        def __init__(self, **kwargs: object) -> None:
            built.append(kwargs)
            self.models = FakeModels()

    monkeypatch.setattr(genai, "Client", FakeClient)
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    return built


def test_the_extraction_backup_gives_up_after_15_seconds(clients: list[dict]) -> None:
    gemini.gemini_model("Load Port: SINGAPORE")

    assert clients[0]["http_options"].timeout == 15_000


def test_the_classification_backup_gives_up_after_15_seconds(clients: list[dict]) -> None:
    gemini.gemini_json("an email")

    assert clients[0]["http_options"].timeout == 15_000


def test_the_scan_reader_gives_up_after_a_minute(clients: list[dict]) -> None:
    """google-genai passes timeout=None when none is given, so a hung call held its
    socket and its worker thread for as long as the server did (#147 B1)."""
    vision.gemini_vision(b"%PDF-1.5")

    assert clients[0]["http_options"].timeout == vision.VISION_TIMEOUT_MS == 60_000


def test_the_reply_drafter_gives_up_when_the_fallback_stops_waiting(clients: list[dict]) -> None:
    reply.make_client("test-key")

    assert clients[0]["http_options"].timeout == reply.GEMINI_REPLY_SECONDS * 1000
