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
DOC_HEADERS: dict[str, str] = {
    "SHIPPING INSTRUCTION": DocumentRoleType.Si,
    "BILL OF LADING INSTRUCTION": DocumentRoleType.Si,
    "BL INSTRUCTION": DocumentRoleType.Si,
    "BILL OF LADING (DRAFT)": DocumentRoleType.Bl,
    "BILL OF LADING": DocumentRoleType.Bl,
}

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


# A number after the title: ": 3043223023", " NO. SIJ6060148", " #12".
TITLE_NUMBER = re.compile(r"\s*(?::|\bNO\.?|#)\s*[A-Z0-9][A-Z0-9/-]*\s*$")


def detect_doc_type(title: str) -> str | None:
    """Map a document's declared title onto SI or BL. Returns the raw title
    when it is neither, which is what makes wrong_doc_type detectable. Never
    looks at the filename - that lies on emails 501-505."""
    header = title.split("\n", 1)[0].strip().upper()
    # "BL INSTRUCTION: 3043223023" and "BILL OF LADING NO. SIJ6060148" carry the
    # document's number on the title line. The title is what comes before it; a
    # title that is not SI or BL is still returned whole, so wrong_doc_type holds.
    titled = TITLE_NUMBER.sub("", header).strip()

    return DOC_HEADERS.get(header) or DOC_HEADERS.get(titled) or header or None
