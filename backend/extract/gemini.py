"""Gemini as the model behind AiExtractor: document text in, seven fields out.

The only module that talks to the network. Structured output means the reply
is always the right shape; the prompt asks for values copied as written,
because normalising is the compare stage's job.
"""
from __future__ import annotations

import os

from pydantic import BaseModel

from backend.contracts import ExtractedField

DEFAULT_MODEL = "gemini-3.5-flash"
# Gemini answers when Qwen is slow, so it gets the same limit per call as Qwen (#111).
TIMEOUT_MS = 15_000
KEY_NAMES = ("GOOGLE_API_KEY", "GEMINI_API_KEY")

PROMPT = """You extract fields from one shipping document (a Shipping Instruction or a Bill of Lading), given as lines of "label: value".
Return these 7 fields: shipper, consignee, notify_party, port_of_loading, port_of_discharge, container_count, gross_weight_kg.
For each field return:
- present: true if the document gives a real value, false if the field is missing, blank, TBA, TBC, N/A, or only underscores.
- label_seen: the label exactly as written, without a trailing colon (for example "To the Order of" is the consignee label). null if not present.
- raw: the value exactly as written, copied character for character. Do not fix, translate, reformat or normalise. For a party or a port, keep only the name, the first segment before any " | ". null if not present.
Ignore every other field (vessel, voyage, HS code, booking, freight).

DOCUMENT:
"""


class FieldValue(BaseModel):
    present: bool
    label_seen: str | None
    raw: str | None


class ModelFields(BaseModel):
    shipper: FieldValue
    consignee: FieldValue
    notify_party: FieldValue
    port_of_loading: FieldValue
    port_of_discharge: FieldValue
    container_count: FieldValue
    gross_weight_kg: FieldValue


def api_key() -> str | None:
    return next((os.environ[name] for name in KEY_NAMES if os.environ.get(name)), None)


def gemini_json(contents: str, system: str | None = None,
                schema: type[BaseModel] | None = None,
                key: str | None = None, model: str | None = None) -> str:
    """The text of one Gemini reply in JSON, for the stages that stand Gemini behind Qwen.
    `key` and `model` replace the defaults, so the classification critic can spend its
    own quota rather than the backup's."""
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=key or api_key(),
                          http_options=types.HttpOptions(timeout=TIMEOUT_MS))
    response = client.models.generate_content(
        model=model or os.environ.get("GEMINI_MODEL", DEFAULT_MODEL),
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction=system,
            temperature=0,
            response_mime_type="application/json",
            response_schema=schema,
        ),
    )
    if not response.text:
        raise RuntimeError("Gemini returned an empty reply")

    return response.text


def gemini_model(text: str) -> dict[str, ExtractedField]:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key(),
                          http_options=types.HttpOptions(timeout=TIMEOUT_MS))
    response = client.models.generate_content(
        model=os.environ.get("GEMINI_MODEL", DEFAULT_MODEL),
        contents=PROMPT + text,
        config=types.GenerateContentConfig(
            temperature=0,
            response_mime_type="application/json",
            response_schema=ModelFields,
        ),
    )

    return {name: {"present": value.present, "label_seen": value.label_seen, "raw": value.raw}
            for name, value in response.parsed}
