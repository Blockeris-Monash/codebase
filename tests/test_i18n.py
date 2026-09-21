"""The page text in frontend/index.html and its built-in translations in frontend/i18n.js stay in step.

Every string the page shows goes through t("English text") or is marked T("English text"), so the
English text is the key. A key without a translation would show in English, so it fails here.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

FRONTEND = Path(__file__).resolve().parents[1] / "frontend"
STRING = r'"((?:[^"\\\n]|\\.)*)"'
PLACEHOLDER = re.compile(r"\{\w+\}")


def page_keys() -> set[str]:
    """Every string the page passes to t() or marks with T(), decoded the way JavaScript reads it."""
    html = (FRONTEND / "index.html").read_text(encoding="utf-8")
    script = html[html.index("<script>\n"):]
    return {json.loads(f'"{m.group(1)}"') for m in re.finditer(r"\b[tT]\(" + STRING, script)}


def built_in() -> dict[str, dict[str, str]]:
    source = (FRONTEND / "i18n.js").read_text(encoding="utf-8")
    lines = [line for line in source.splitlines() if not line.startswith("//")]
    body = "\n".join(lines).strip().removeprefix("window.I18N =").removesuffix(";")
    return json.loads(body)


def test_every_page_string_has_a_malay_and_a_chinese_translation() -> None:
    keys, languages = page_keys(), built_in()
    for code in ("ms", "zh"):
        assert keys - set(languages[code]) == set(), f"{code} is missing translations"


def test_the_translations_hold_no_string_the_page_does_not_use() -> None:
    keys, languages = page_keys(), built_in()
    for code in ("ms", "zh"):
        assert set(languages[code]) - keys == set(), f"{code} has strings the page never shows"


def test_a_translation_keeps_the_placeholders_of_its_english_text() -> None:
    for code, table in built_in().items():
        for english, translated in table.items():
            assert sorted(PLACEHOLDER.findall(english)) == sorted(PLACEHOLDER.findall(translated)), (
                f"{code}: {english!r}")


def test_no_translation_is_blank() -> None:
    for table in built_in().values():
        assert all(text.strip() for text in table.values())
