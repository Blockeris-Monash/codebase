"""Aligning a document's own label text onto the seven compared fields.

Its own module because both the readers and the extractor need it, and
read_documents cannot import make_fixtures without a cycle.
"""
from __future__ import annotations

import re

from backend.contracts import DocumentRoleType

# Label variants observed across the corpus, aligned by meaning not by text.
# Matched AFTER prefixes, parentheticals and CJK are stripped, so
# "Gross Wt (kgs)", "Gross Weight (KG)", "Gross Weight毛重(KGS)" and
# "TOTAL Gross Weight■■(KGS)" all arrive as "gross wt" / "gross weight".
LABEL_PATTERNS: dict[str, list[str]] = {
    "shipper": [r"^shipper(/exporter)?$"],
    "consignee": [r"^consignee$", r"^to the order of$"],
    "notify_party": [r"^notify( party)?$", r"^notify party/intermediate consignee$"],
    "port_of_loading": [r"^port of loading$", r"^load port$", r"^pol$"],
    "port_of_discharge": [r"^port of discharge$", r"^discharge port$", r"^pod$"],
    "container_count": [r"^(total )?containers?( count)?$",
                        r"^no\. of containers( or packages)?$"],
    "gross_weight_kg": [r"^gross wt kgs?$", r"^gross wt$", r"^gross weight$"],
}

# An SI is titled differently by format. The .txt files say "SHIPPING
# INSTRUCTION", Excel says "BL INSTRUCTION", the PDFs use the industry's own
# name, "BILL OF LADING INSTRUCTION". All three are the shipper instructing
# the carrier.
# By wording, not exact lines (#147 B3); SI first, as "BILL OF LADING INSTRUCTION" is an SI.
SI_TITLE = re.compile(r"^(?:SHIPPING|BILL OF LADING|B/?L)\s+INSTRUCTIONS?\b")
BL_TITLE = re.compile(r"^(?:(?:DRAFT|OCEAN|HOUSE|MASTER|NON-?NEGOTIABLE)\s+)*"
                      r"(?:BILL OF LADING|B/L|SEA\s*WAYBILL)\b(?!\s+INSTRUCTION)")
DOC_TITLES: tuple[tuple[re.Pattern[str], str], ...] = (
    (SI_TITLE, DocumentRoleType.Si),
    (BL_TITLE, DocumentRoleType.Bl),
)

CJK_PATTERN = r"[一-鿿]"
# pypdf substitutes U+25A0 for a glyph it cannot map. In this corpus that is
# always the CJK in a label, so it gets the same treatment.
UNMAPPED_GLYPH = "■"
PARENTHETICAL = r"\([^)]*\)"
# A PDF totals row reads "TOTAL Gross Weight (KG)". The prefix is presentation.
LABEL_PREFIXES = r"^(total)\s+"


def is_label_match(plain: str, field: str) -> bool:
    return any(re.match(p, plain) for p in LABEL_PATTERNS[field])


def canonical_field(label: str) -> str | None:
    """Map a document's own label text onto one of the seven field names."""
    plain = re.sub(CJK_PATTERN, "", label).replace(UNMAPPED_GLYPH, "")
    plain = re.sub(PARENTHETICAL, " ", plain)
    plain = re.sub(r"\s+", " ", plain).strip().lower()
    plain = re.sub(LABEL_PREFIXES, "", plain)

    return next((f for f in LABEL_PATTERNS if is_label_match(plain, f)), None)


def detect_doc_type(title: str) -> str | None:
    """Map a document's declared title onto SI or BL. Returns the raw title
    when it is neither, which is what makes wrong_doc_type detectable. Never
    looks at the filename - that lies on emails 501-505."""
    header = title.split("\n", 1)[0].strip().upper()
    words = re.sub(r"\s+", " ", header)

    return next((role for pattern, role in DOC_TITLES if pattern.match(words)), header or None)
