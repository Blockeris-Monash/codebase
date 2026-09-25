"""Stage 3 with an AI model: Lane A's label/value pairs in, the seven fields out.

Lane A owns reading the file, the document type and parse_status. This module
only decides which pair is which of the seven fields, so it can be used where
the rule-based make_fixtures.fields_from_pairs is used today. The model only
ever sees text, never a binary file.
"""
from __future__ import annotations

import logging
import re
import time
from collections.abc import Callable
from dataclasses import dataclass

from backend.contracts import ExtractedField
from backend.read.labels import canonical_field
from backend.security.pii import get_pii_masker

log = logging.getLogger(__name__)

DEFAULT_TRIES = 3
DEFAULT_WAIT_SECONDS = 2.0
ModelCall = Callable[[str], dict[str, ExtractedField]]
LabelledPairs = list[tuple[str, str]]


def squash(text: str) -> str:
    return " ".join(text.split())


def is_under_its_label(raw: str, label_seen: str | None, pairs: LabelledPairs) -> bool:
    """The value appears whole under the label the model says it read.

    A substring of the whole document let the shipper's name through as the consignee,
    "100" out of "12,100" and "1" out of "1 lot" (#147 A3). Whole tokens only, and only
    from pairs whose label starts with the one the model named - any pair when it
    named none."""
    # Not glued to a letter, digit or number separator: "100" is not in "12,100".
    value = re.compile(rf"(?<![\w.,]){re.escape(squash(raw))}(?![\w]|[.,]\d)")
    wanted = plain_label(label_seen or "")

    return any(value.search(squash(text)) for label, text in pairs
               if is_same_label(plain_label(label), wanted))


def plain_label(label: str) -> str:
    """A label as words only: "Consignee (Name):" and "CONSIGNEE" are the same label."""
    return " ".join(re.sub(r"\([^)]*\)|[^\w\s/]", " ", label).split()).lower()


def is_same_label(in_document: str, named: str) -> bool:
    """Either one starts with the other, so a model that shortens or completes a label
    still finds it; an empty name matches every pair."""
    return in_document.startswith(named) or named.startswith(in_document)


def is_misplaced(name: str, value: ExtractedField, pairs: LabelledPairs) -> bool:
    """Read from a label the rules know belongs to another field, or not found under its own."""
    claimed = canonical_field(value["label_seen"] or "")
    if claimed is not None and claimed != name:
        return True

    return not is_under_its_label(value["raw"] or "", value["label_seen"], pairs)


def keep_only_values_under_their_label(email_id: str, fields: dict[str, ExtractedField],
                                       pairs: LabelledPairs) -> dict[str, ExtractedField]:
    """A value not found whole under its own label was invented, altered or taken from
    another field, so that field is reported as absent."""
    checked: dict[str, ExtractedField] = {}
    for name, value in fields.items():
        if value["present"] and is_misplaced(name, value, pairs):
            log.warning("%s %s: value not found under label %r, rejected", email_id, name, value["label_seen"])
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

        return keep_only_values_under_their_label(email_id, fields, pairs)
