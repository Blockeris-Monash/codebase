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

from backend.contracts import ExtractedField
from backend.security.pii import get_pii_masker

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
    deadline: float | None = None  # seconds for all tries together; None means no limit

    def ask_model(self, email_id: str, text: str) -> dict[str, ExtractedField] | None:
        """Retry a failing model; None means it never answered.

        No attempt and no wait starts once `deadline` seconds have passed. A call
        already running is not cut short here: each model call has its own timeout.

        The deadline is checked before an attempt as well as before the wait,
        because one "attempt" can be two model calls - `with_fallback` tries the
        second provider inside it - so an attempt begun at 44 s of a 45 s budget
        could still run for another 30. Checking only before the wait made the
        real ceiling `deadline + one whole attempt`."""
        give_up_at = None if self.deadline is None else time.monotonic() + self.deadline
        for attempt in range(1, self.tries + 1):
            if give_up_at is not None and attempt > 1 and time.monotonic() >= give_up_at:
                log.warning("%s gave up before attempt %d/%d: the %gs deadline has passed",
                            email_id, attempt, self.tries, self.deadline)
                break
            try:
                return self.model(text)
            except Exception as error:
                log.warning("%s attempt %d/%d failed: %s", email_id, attempt, self.tries, error)
            if attempt == self.tries:
                break
            pause = self.wait * attempt
            if give_up_at is not None and time.monotonic() + pause >= give_up_at:
                log.warning("%s gave up after attempt %d/%d: the %gs deadline has passed",
                            email_id, attempt, self.tries, self.deadline)
                break
            time.sleep(pause)

        return None

    def extract_fields(self, email_id: str,
                       pairs: LabelledPairs) -> dict[str, ExtractedField] | None:
        """The seven fields for one document, or None if the model never answered.
        PII (phone numbers, personal emails, bank details) is masked before AI call,
        while shipper, consignee, and notify party are strictly preserved.
        """
        masker = get_pii_masker()
        masked_pairs = masker.mask_document_pairs(pairs)
        text = pairs_as_text(masked_pairs)
        fields = self.ask_model(email_id, text)
        if fields is None:
            return None

        orig_text = pairs_as_text(pairs)
        return keep_only_values_in_text(email_id, fields, orig_text)
