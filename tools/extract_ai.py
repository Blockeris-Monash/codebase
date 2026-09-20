"""Stage 3 with an AI model: Lane A's label/value pairs in, the seven fields out.

Lane A owns reading the file, the document type and parse_status. This module
only decides which pair is which of the seven fields, so it can be used where
the rule-based make_fixtures.fields_from_pairs is used today. The model only
ever sees text, never a binary file.
"""
from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass

from contract_types import ExtractedField

log = logging.getLogger(__name__)

DEFAULT_TRIES = 3
DEFAULT_WAIT_SECONDS = 2.0
ModelCall = Callable[[str], dict[str, ExtractedField]]
LabelledPairs = list[tuple[str, str]]


def squash(text: str) -> str:
    return " ".join(text.split())


def keep_only_values_in_text(email_id: str, fields: dict[str, ExtractedField],
                             text: str) -> dict[str, ExtractedField]:
    """A raw value that is not in the document was invented or altered by the
    model, so that field is reported as absent."""
    haystack = squash(text)
    checked: dict[str, ExtractedField] = {}
    for name, value in fields.items():
        if value["present"] and squash(value["raw"] or "") not in haystack:
            log.warning("%s %s: %r not found in document, rejected",
                        email_id, name, value["raw"])
            value = {"present": False, "label_seen": None, "raw": None}
        checked[name] = value

    return checked


def pairs_as_text(pairs: LabelledPairs) -> str:
    return "\n".join(f"{label}: {value}" for label, value in pairs)


@dataclass(frozen=True)
class AiExtractor:
    model: ModelCall
    tries: int = DEFAULT_TRIES
    wait: float = DEFAULT_WAIT_SECONDS

    def ask_model(self, email_id: str, text: str) -> dict[str, ExtractedField] | None:
        """Retry a failing model; None means it never answered."""
        for attempt in range(1, self.tries + 1):
            try:
                return self.model(text)
            except Exception as error:
                log.warning("%s attempt %d/%d failed: %s", email_id, attempt, self.tries, error)
                if attempt < self.tries:
                    time.sleep(self.wait * attempt)

        return None

    def extract_fields(self, email_id: str,
                       pairs: LabelledPairs) -> dict[str, ExtractedField] | None:
        """The seven fields for one document, or None if the model never answered."""
        text = pairs_as_text(pairs)
        fields = self.ask_model(email_id, text)
        if fields is None:
            return None

        return keep_only_values_in_text(email_id, fields, text)
