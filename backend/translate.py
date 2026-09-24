"""Translate an email and its documents with Qwen, for the UI's Translate button.

Same gateway and key as the extractor, and the same Gemini backup when Qwen fails
or stalls and a Gemini key is set. The model is asked to return one JSON
object with the same keys it was given, so the caller can put each text back
where it came from.
"""
from __future__ import annotations

import json
import os
from functools import partial

from backend.extract.fallback import with_fallback
from backend.extract.gemini import api_key as gemini_key, gemini_json
from backend.extract.qwen import DEFAULT_BASE_URL, DEFAULT_MODEL, USER_AGENT, Post, http_post, json_in

from backend.security.pii import get_pii_masker

MAX_CHARS = 30000  # everything in one request, so one email and its two documents fit


class TranslationFailed(Exception):
    """The model did not return usable JSON."""


class TooMuchText(ValueError):
    """The request is longer than one call should carry."""


PROMPT = (
    "Translate the value of every key in the JSON object below into {target}. "
    "Keep company names, person names, port names, container numbers, reference numbers and "
    "codes exactly as written. Keep placeholder tokens like {{PHONE_NUMBER_1}} or {{EMAIL_ADDRESS_1}} unchanged. Keep the line breaks. "
    "Reply with only one JSON object that has the same keys.\n\n"
)


def parse_reply(reply_text: str) -> dict:
    try:
        translated = json.loads(json_in(reply_text))
    except json.JSONDecodeError as error:
        raise TranslationFailed(f"the reply is not JSON: {error}") from error
    if not isinstance(translated, dict):
        raise TranslationFailed("the reply is not a JSON object")

    return translated


def qwen_translation(message: str, post: Post = http_post) -> dict:
    key = os.environ.get("QWEN_API_KEY")
    if not key:
        raise RuntimeError("QWEN_API_KEY is not set")

    base_url = os.environ.get("QWEN_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
    reply = post(
        f"{base_url}/v1/messages",
        {"content-type": "application/json", "anthropic-version": "2023-06-01",
         "x-api-key": key, "user-agent": USER_AGENT},
        {"model": os.environ.get("QWEN_MODEL", DEFAULT_MODEL), "max_tokens": 4096, "temperature": 0,
         "messages": [{"role": "user", "content": message}]})

    return parse_reply("".join(block.get("text", "") for block in reply["content"]))


def gemini_translation(message: str) -> dict:
    return parse_reply(gemini_json(message))


def translate_texts(texts: dict[str, str], target: str, post: Post = http_post) -> dict[str, str]:
    """Each text translated into `target`. Blank texts and texts the model skips come back unchanged.
    PII (phone numbers, personal emails, bank details) is reversibly masked before LLM call and restored.
    """
    if sum(len(text) for text in texts.values()) > MAX_CHARS:
        raise TooMuchText(f"more than {MAX_CHARS} characters")

    todo = {key: text for key, text in texts.items() if text.strip()}
    if not todo:
        return dict(texts)

    masker = get_pii_masker()
    anonymized_todo: dict[str, str] = {}
    mappings: dict[str, dict[str, str]] = {}

    for key, text in todo.items():
        anon_text, pii_map = masker.anonymize_reversible(text)
        anonymized_todo[key] = anon_text
        mappings[key] = pii_map

    # Qwen first, Gemini when Qwen fails or stalls, only when a Gemini key is set (as in extraction).
    model = with_fallback(partial(qwen_translation, post=post), gemini_translation,
                          enabled=lambda: bool(gemini_key()))
    translated = model(PROMPT.format(target=target) + json.dumps(anonymized_todo, ensure_ascii=False))

    result: dict[str, str] = {}
    for name, text in texts.items():
        if isinstance(translated.get(name), str) and name in todo:
            # Restore original PII tokens after translation so human UI user sees real info
            restored_text = masker.deanonymize(translated[name], mappings.get(name, {}))
            result[name] = restored_text
        else:
            result[name] = text

    return result
