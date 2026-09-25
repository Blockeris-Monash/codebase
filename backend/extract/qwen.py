"""Qwen as the model behind AiExtractor: same shape as gemini_model.

Talks to an Anthropic-style /v1/messages endpoint. The base URL and key come
from the environment, so a teammate can point at a shared proxy without ever
holding the real key.
"""
from __future__ import annotations

import json
import os
import urllib.request
from typing import Callable

from pydantic import ValidationError

from backend.contracts import ExtractedField
from backend.extract.gemini import PROMPT, ModelFields

DEFAULT_BASE_URL = "https://gateway.9arm.co"
DEFAULT_MODEL = "qwen3.8-27b-fp8"
USER_AGENT = "hackathon-extractor/0.1"  # the gateway's Cloudflare blocks requests without one
# A normal call answers in 5 to 7 s; on a slow night it takes about 48 s, too late to be of use
# (#109). 15 s never cuts off a healthy call. Classification uses http_post too.
DEFAULT_TIMEOUT_SECONDS = 15.0

Post = Callable[[str, dict, dict], dict]


def http_post(url: str, headers: dict, body: dict, timeout: float | None = None) -> dict:
    """One call. `timeout` lets a caller with a deadline give a try less than the usual limit."""
    request = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers)
    usual = float(os.environ.get("QWEN_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS))
    timeout = usual if timeout is None else min(timeout, usual)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


def json_in(reply_text: str) -> str:
    """The JSON object in a reply, ignoring blank lines and code fences."""
    start, end = reply_text.find("{"), reply_text.rfind("}")
    return reply_text[start:end + 1] if start != -1 and end > start else reply_text


def qwen_model(text: str, post: Post = http_post) -> dict[str, ExtractedField]:
    key = os.environ.get("QWEN_API_KEY")
    if not key:
        raise RuntimeError("QWEN_API_KEY is not set")

    base_url = os.environ.get("QWEN_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
    reply = post(
        f"{base_url}/v1/messages",
        {"content-type": "application/json", "anthropic-version": "2023-06-01",
         "x-api-key": key, "user-agent": USER_AGENT},
        {"model": os.environ.get("QWEN_MODEL", DEFAULT_MODEL), "max_tokens": 4096,
         "temperature": 0,
         "messages": [{"role": "user", "content":
                       PROMPT + text + "\n\nReply with only one JSON object with these 7 keys."}]})

    reply_text = "".join(block.get("text", "") for block in reply["content"])
    try:
        parsed = ModelFields.model_validate_json(json_in(reply_text))
    except ValidationError as error:
        raise ValueError(f"Qwen reply is not the 7 fields: {error}") from error

    return {name: {"present": value.present, "label_seen": value.label_seen, "raw": value.raw}
            for name, value in parsed}
