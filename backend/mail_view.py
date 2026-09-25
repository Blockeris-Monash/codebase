"""What the page draws for one email, shared by the live service and cli/make_results.py.

The live mailbox and the demo build must show an email the same way, so these live in the
backend and the CLI imports them; the backend used to import them from the CLI, and the
CLI imports the backend, which made each depend on the other (#147 B4).
"""
from __future__ import annotations

import re
from pathlib import Path

from backend.contracts import CategoryType, ParseStatusType
from backend.read.documents import document_title, read_document

BODY_LIMIT = 1500

COMPARE_ASK = re.compile(
    r"(check|verify|compare|confirm)\w*\b.{0,40}\bdraft\s+BL\b.{0,40}\b(against|with|vs\.?)\b.{0,20}\bSI\b",
    re.I | re.S,
)
# An email that asks someone to send the draft BL and has nothing attached. There is nothing to
# compare yet, so the UI files it under its own folder instead of Needs review.
DRAFT_REQUEST = re.compile(r"\b(send|provide)\b.{0,30}\bdraft\s+BL\b", re.I | re.S)
SPAM = re.compile(r"bitcoin|exclusive offer|storage is|valued customer|increase your|approval required|prize|winner", re.I)
INVOICE = re.compile(r"invoice|billing|charges|debit note|payment|\bsoa\b", re.I)
SI_ASK = re.compile(r"\bSI\b|shipping instruction|draft\s+BL", re.I)

# The shipment a message is about, so a reviewer can answer "Commercial is asking about
# 5ALT-01226" without opening anything. Two shapes appear in this corpus and nothing else
# does: an order reference (5ALT-01226) and a carrier booking reference (OOLU9284044566).
#
# The carrier half demands a run of four digits. Without it, "[A-Z]{4}[A-Z0-9]{6,}" also
# matches INTERNATIONAL, OUTSTANDING and INVESTMENT - 13 English words in these subjects
# alone, every one of them a false reference on a reviewer's screen.
SHIPMENT_REF = re.compile(r"\b(?:\d[A-Z]{3}-\d{4,6}|[A-Z]{4}[A-Z0-9]*\d{4,}[A-Z0-9]*)\b")


def shipment_ref(subject: str, body: str) -> str | None:
    """The shipment this email is about, or None.

    Subject before body, and first match within each, so the reference shown on a row is
    the one already visible in the list rather than something found further down.
    """
    for text in (subject, body):
        found = SHIPMENT_REF.search((text or "").upper())
        if found:
            return found.group(0)
    return None


def fallback_category(subject: str, body: str, n_attachments: int) -> str:
    if n_attachments >= 1 or COMPARE_ASK.search(body):
        return CategoryType.BlComparison
    text = f"{subject} {body[:300]}"
    if SPAM.search(text):
        return CategoryType.Spam
    if INVOICE.search(text):
        return CategoryType.InvoiceQuery
    if SI_ASK.search(text):
        return CategoryType.SiRequest
    return CategoryType.General


def clean_body(body: str) -> str:
    return re.sub(r"\n{3,}", "\n\n", body).strip()[:BODY_LIMIT]


def document(path: Path, saved_status: str | None = None) -> dict:
    """What the UI needs from one attachment: shown text, and the inputs for a live re-check.
    `saved_status` is the parse status a saved extract recorded for it, when there is one."""
    out = {"name": path.name, "format": path.suffix.lstrip("."), "title": None, "pairs": [],
           "text": None, "parse_status": saved_status or ParseStatusType.Ok}
    try:
        out["title"] = document_title(path)
        _, pairs = read_document(path)
        out["pairs"] = [list(p) for p in pairs]
    except Exception:  # unreadable files are Lane A's escalation, the comparator handles them
        out["parse_status"] = saved_status or ParseStatusType.Unreadable
    if path.suffix == ".txt":
        out["text"] = path.read_text(encoding="utf-8", errors="replace")
    elif out["pairs"]:
        out["text"] = "\n".join(f"{label}: {value}" for label, value in out["pairs"])
    return out
