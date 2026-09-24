"""Is this a value these documents actually use?

A value read from text can be checked against the text it came from. A value
read from a scanned page cannot - the characters are not in the file. The
corpus is the next best anchor: six of the seven fields draw on a small closed
set across the 192 text attachments, so a scanned reading outside that set is
far more likely to be a transcription slip than a party appearing for the first
time on an image-only page.

Measured on the six scans: the model produced 11 values outside the vocabulary,
and every one was an error - a missing space (AL GURG STATIONERYLLC), an
invented comma (APRIL, FINE PAPER TRADING), and ports that lost their country
(NHAVA SHEVA for NHAVA SHEVA, INDIA). Reading the pages by eye confirmed all
eleven.

THIS IS NOT FUZZY MATCHING. Nothing is corrected towards a near neighbour, and
no similarity threshold is involved: the entity pool contains deliberately
near-identical parties, and anything loose enough to merge a scanning artefact
would merge two real companies and take a planted defect with it. The only
question asked is whether the exact normalised value has been seen before, and
the only answer that changes anything is "no".
"""
from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path

from backend.compare.normalise import normalise

log = logging.getLogger(__name__)

VOCABULARY_FILE = Path(__file__).resolve().parents[2] / "results" / "vocabulary.json"


@lru_cache(maxsize=1)
def vocabulary() -> dict[str, frozenset[str]]:
    """The closed sets, or empty when the file is absent - in which case every
    value is treated as known and this check simply does nothing."""
    try:
        raw = json.loads(VOCABULARY_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        log.warning("no vocabulary at %s (%s); scanned values go unchecked",
                    VOCABULARY_FILE.name, error)
        return {}

    return {field: frozenset(values) for field, values in raw.items()}


def is_checkable(field: str) -> bool:
    """False where the corpus has no closed set - gross weight takes free
    values, so "not in the list" would mean nothing there."""
    return field in vocabulary()


def is_known(field: str, raw: str | None) -> bool:
    """True when this exact value, normalised, has been seen in the corpus.

    True for anything unchecked, so a field with no closed set and a document
    with no vocabulary both behave exactly as they did before.
    """
    if not is_checkable(field):
        return True
    normalised = normalise(field, raw)
    if normalised is None:
        return True                      # absent already escalates on its own

    return normalised in vocabulary()[field]


def untrusted_fields(fields: dict[str, dict]) -> list[str]:
    """The fields whose value this corpus has never seen, in field order."""
    return [name for name, value in fields.items()
            if value.get("present") and not is_known(name, value.get("raw"))]
