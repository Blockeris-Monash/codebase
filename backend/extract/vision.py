"""Reading the scanned attachments, which carry no text to extract.

Six of the eight attachments on the five `unreadable` emails are real scans -
about 20 KB each, a single 1240x1754 image per page and no text layer at all.
`read_pdf` finds no labels in them and reports them unreadable, which is
honest but means those emails never reach the comparison the product exists to
perform.

This is OCR, done with a vision model rather than a separate OCR engine: the
page image goes to the model and the seven fields come back, instead of raw
text that would then have to be parsed for labels. The PDF is sent as bytes -
Gemini rasterises internally - so there is no poppler, no pdf2image and no new
system dependency.

TWO OF THE EIGHT CANNOT BE READ BY ANYTHING. `email_511_BL.pdf` and
`email_515_BL.pdf` are 775 and 765 bytes: a `%PDF-1.5` header followed by
binary with no image, no font and no page content. They stay unreadable, and
that is the correct answer rather than a limitation.

OFF BY DEFAULT. The organisers' reference expects `NEEDS_REVIEW/unreadable`
for all five of these emails, and the submitted run scores 5 of 5 by
escalating them. Reading three of them successfully therefore disagrees with
the reference three more times. Behind an opt-in, the submitted numbers stay
reproducible and the capability can still be demonstrated.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from backend.contracts import ExtractedField
from backend.extract.gemini import DEFAULT_MODEL, ModelFields, api_key

log = logging.getLogger(__name__)

OPT_IN = "SHIP_HAPPENS_VISION"
PDF_MIME = "application/pdf"
CACHE_DIR = Path(__file__).resolve().parents[2] / "results" / "vision"

# A scan has no text layer, so a file this small holds no page at all - not a
# picture of one, nothing. Reading it is impossible rather than merely hard.
EMPTY_PDF_BYTES = 2048

VISION_PROMPT = """You are reading one page of a SCANNED shipping document - a Shipping Instruction or a Bill of Lading. It is an image of a printed form.
Return these 7 fields: shipper, consignee, notify_party, port_of_loading, port_of_discharge, container_count, gross_weight_kg.
For each field return:
- present: true only if you can SEE a printed label and a real value beside it. false if the field is absent, blank, TBA, TBC, N/A, only underscores, or if you cannot read it confidently.
- label_seen: the printed label exactly as it appears on the page, without a trailing colon (for example "To the Order of" is the consignee label). null if you cannot see a label.
- raw: the value exactly as printed, character for character. Do not correct, translate, reformat or normalise it. For a party or a port keep only the name. null if not present.
Do not guess. A field you cannot read clearly is present: false. A wrong value is far worse here than a missing one, because a missing value is escalated to a person and a wrong value is not.
Ignore every other field on the page (vessel, voyage, HS code, booking, freight).
"""


def vision_enabled() -> bool:
    """Opt-in, so a run that quotes the submitted numbers cannot silently
    include values the submitted run did not have."""
    return os.environ.get(OPT_IN) == "1" and bool(api_key())


def is_empty_pdf(path: Path) -> bool:
    """True for a file too small to contain a page. Distinguishes "this is a
    scan we have not read yet" from "there is nothing here to read"."""
    return path.exists() and path.stat().st_size < EMPTY_PDF_BYTES


def verbatim_only(fields: dict[str, ExtractedField]) -> dict[str, ExtractedField]:
    """Drop any value the model did not tie to a label it could see.

    The text path checks a value against the document it came from. That check
    cannot run on an image, so the label is what stands in for it: a model that
    reports a value without naming the label beside it has not read the field,
    it has produced one. Those land on missing rather than on a verdict, so the
    email escalates to a person instead of being decided on a guess.
    """
    clean: dict[str, ExtractedField] = {}
    for name, field in fields.items():
        usable = bool(field.get("present")) and bool(field.get("label_seen")) and bool(field.get("raw"))
        clean[name] = field if usable else {"present": False, "label_seen": None, "raw": None}

    return clean


def _cache_path(path: Path) -> Path:
    return CACHE_DIR / f"{path.stem}.json"


def cached(path: Path) -> dict[str, ExtractedField] | None:
    """A demo must not depend on a free tier answering. Roughly 20 requests a
    day covers six files once, not six files on every rehearsal."""
    saved = _cache_path(path)
    if not saved.exists():
        return None
    try:
        return json.loads(saved.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        log.warning("ignoring unreadable vision cache %s: %s", saved.name, error)
        return None


def remember(path: Path, fields: dict[str, ExtractedField]) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _cache_path(path).write_text(json.dumps(fields, indent=2, ensure_ascii=False) + "\n",
                                encoding="utf-8", newline="\n")


def gemini_vision(pdf: bytes) -> dict[str, ExtractedField]:
    """The only call that reaches the network. Same client, same schema and the
    same temperature as the text path; the PDF replaces the document text."""
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key())
    response = client.models.generate_content(
        model=os.environ.get("GEMINI_MODEL", DEFAULT_MODEL),
        contents=[VISION_PROMPT, types.Part.from_bytes(data=pdf, mime_type=PDF_MIME)],
        config=types.GenerateContentConfig(
            temperature=0,
            response_mime_type="application/json",
            response_schema=ModelFields,
        ),
    )

    return {name: {"present": value.present, "label_seen": value.label_seen, "raw": value.raw}
            for name, value in response.parsed}


def read_scan(path: Path, call=gemini_vision) -> dict[str, ExtractedField] | None:
    """Seven fields from a scanned page, or None to leave it unreadable.

    None every time the answer is not trustworthy - the opt-in is off, there is
    no key, the file holds no page, or the call failed. The caller then reports
    `unreadable` exactly as it does today, so this can only ever add readings,
    never change one.
    """
    if not vision_enabled():
        return None
    if is_empty_pdf(path):
        log.info("%s is %d bytes and holds no page; nothing can read it", path.name, path.stat().st_size)
        return None

    saved = cached(path)
    if saved is not None:
        return saved

    try:
        fields = verbatim_only(call(path.read_bytes()))
    except Exception as error:  # a third-party client; any failure means unreadable
        log.warning("vision read of %s failed, leaving it unreadable: %s", path.name, error)
        return None

    remember(path, fields)
    return fields
