"""Stage 2 with an AI model: one attachment in, one DocumentExtract out.

Same contract and same three-argument call as the rule-based
make_fixtures.document_extract, so the two can be compared field by field.
The reader turns any format into label/value pairs first; the model only ever
sees that text, never a binary file.
"""
from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from contract_types import Attachment, DocumentExtract, ExtractedField, ParseStatusType
from labels import detect_doc_type
from make_fixtures import absent_fields
from read_documents import document_title, read_document

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

    def document_extract(self, data_dir: str, email_id: str,
                         meta: Attachment) -> DocumentExtract:
        base: DocumentExtract = {
            "email_id": email_id,
            "declared_role": meta["declared_role"],
            "source_path": meta["path"],
            "format": meta["format"],
            "detected_doc_type": None,
            "parse_status": ParseStatusType.NotAttempted,
            "fields": absent_fields(),
        }
        path = Path(data_dir) / meta["path"]
        status, pairs = read_document(path)
        if status != ParseStatusType.Ok:
            return {**base, "parse_status": status}

        doc_type = detect_doc_type(document_title(path) or "")
        text = pairs_as_text(pairs)
        fields = self.ask_model(email_id, text)
        if fields is None:
            return {**base, "detected_doc_type": doc_type,
                    "parse_status": ParseStatusType.Unreadable}

        return {**base, "detected_doc_type": doc_type,
                "parse_status": ParseStatusType.Ok,
                "fields": keep_only_values_in_text(email_id, fields, text)}
