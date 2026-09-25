"""What the sender wants, and a plain-English title, for each email.

The classifier's five categories say which queue an email goes in. The intent is one step
finer (an invoice email may be a cancellation, a missing GR, a D&D charge or a question on
local charges), and `about` gives the few words a title needs: who and where for a shipment,
the invoice number, or the vessel. The page builds the title from both, in its own language:

    "New Shipping Instruction: ROXCEL TRADING GMBH · Apapa, Nigeria"

Plain rules, not a model: the classifier and its saved results are untouched, and a wording
no rule knows gets no intent, so the page keeps showing the subject rather than a guess.
tests/test_intent.py checks the rules against a hand label for every organizer email.
"""
from __future__ import annotations

import re

# intent: (the category it sits in, the label the page shows)
INTENTS: dict[str, tuple[str, str]] = {
    "check_draft_bl": ("BL_COMPARISON", "Check draft BL against SI"),
    "chase_draft_bl": ("BL_COMPARISON", "Draft BL requested"),
    "resend_documents": ("BL_COMPARISON", "Attachments missing"),
    "submit_si": ("SI_REQUEST", "New Shipping Instruction"),
    "cancel_invoice": ("INVOICE_QUERY", "Cancel invoice"),
    "missing_gr": ("INVOICE_QUERY", "GR missing for invoice"),
    "dd_charges": ("INVOICE_QUERY", "Confirm D&D charges"),
    "charge_query": ("INVOICE_QUERY", "Question on invoice charges"),
    "system_notice": ("GENERAL", "System notice, no action needed"),
    "schedule_update": ("GENERAL", "Vessel update"),
    "outstanding_reminder": ("GENERAL", "Outstanding items reminder"),
    "office_notice": ("GENERAL", "Office notice"),
}

# The list row is about 45 characters wide, so it uses these; the heading uses the full label.
SHORT: dict[str, str] = {
    "check_draft_bl": "SI vs BL", "chase_draft_bl": "BL requested", "resend_documents": "Files missing",
    "submit_si": "New SI", "cancel_invoice": "Cancel invoice", "missing_gr": "GR missing",
    "dd_charges": "D&D charges", "charge_query": "Charges query", "system_notice": "System notice",
    "schedule_update": "Vessel update", "outstanding_reminder": "Outstanding items",
    "office_notice": "Office notice",
}

# Tried in order within a category; the first match wins. The order matters where two could
# match: an automated notice says "no action required" whatever else it mentions.
RULES: dict[str, list[tuple[str, re.Pattern[str]]]] = {
    "BL_COMPARISON": [
        ("resend_documents", re.compile(r"\bdropped\b|\bstill missing\b|\bnot attached\b", re.I)),
    ],
    "INVOICE_QUERY": [
        ("cancel_invoice", re.compile(r"\bcancel", re.I)),
        ("missing_gr", re.compile(r"\bGR\b")),
        ("dd_charges", re.compile(r"\bD\s?&\s?D\b|detention|demurrage", re.I)),
        ("charge_query", re.compile(r"\bTHC\b|local charge|breakdown", re.I)),
    ],
    "GENERAL": [
        ("system_notice", re.compile(r"automated notification|no action required", re.I)),
        ("schedule_update", re.compile(r"\bberth|loading completed|\bETA\b", re.I)),
        ("outstanding_reminder", re.compile(r"\boutstanding\b|\bpending\b|\breminder\b", re.I)),
        ("office_notice", re.compile(r"new year|holiday|office (?:closed|resumes)", re.I)),
    ],
}
# The whole category is one intent unless a rule above says otherwise.
DEFAULT = {"BL_COMPARISON": "check_draft_bl", "SI_REQUEST": "submit_si"}


def email_intent(category: str, subject: str, body: str, awaiting: bool = False) -> str | None:
    """The intent inside `category`, or None when no rule knows this wording.

    `awaiting` is make_results' own test for a draft BL request with nothing attached, so
    the chase list and the "Draft BL requests" folder always hold the same emails.
    """
    if category == "BL_COMPARISON" and awaiting:
        return "chase_draft_bl"
    for intent, pattern in RULES.get(category, []):
        if pattern.search(body or ""):
            return intent
    return DEFAULT.get(category)


# Shipment subjects in this corpus come in two shapes, and both name the destination and
# the customer:
#   AIE - CALLAO_PERU - YM(YMJAI926322399) - 5RVN-11404 - 5250072886 - CUSTOMER - CFR
#   TO CONFIRM DOCS _ 5RVN-06271 _ MERSIN_TURKEY _ CUSTOMER _ OOLU0811260030
DASHED = re.compile(r"^(?:RE_ )?[A-Z]+ - ([A-Z .]+_[A-Z .]+) - [A-Z]+\(\w+\) - \w+-\w+ - \d+ - (.+?) - \w+$")
UNDERSCORED = re.compile(r"^(?:RE_ )?(?:TO CONFIRM DOCS|REQUEST SI) _ [\w-]+ _ ([A-Z .]+_[A-Z .]+) _ (.+?) _ \w+$")
# An SI subject names only the destination; the customer is the SI's consignee.
SI_SUBJECT = re.compile(r"^(?:RE_ )?SI - \w+ - [^-]+ - [\w-]+ - ([A-Z .]+_[A-Z .]+) - ")
# The other two shapes name only the vessel or the purchase order:
#   RE_ Draft BL LE HAVRE V.QI540A NANTONG - amend BL 042
#   REQUEST BL DRAFT _ PO 25041_ PAPERONE DIGITAL COPIER PAPER__120MT
DRAFT_BL_VESSEL = re.compile(r"^(?:RE_ )?Draft BL (.+? V\.\w+) ")
PO = re.compile(r"^(?:RE_ )?REQUEST BL DRAFT _ (PO \d+)")
CONSIGNEE = re.compile(r"^Consignee:\s*\n\s*(.+)$", re.M)
POD = re.compile(r"^POD:\s*(.+)$", re.M)

INVOICE_NO = re.compile(r"\binvoice (\d{6,})", re.I)
CANCEL_FOR = re.compile(r"\bcancel invoice \d+ for (.+?) \(", re.I)
CHARGES_FOR = re.compile(r"\bcharges for (\w+)", re.I)
VESSEL = re.compile(r"\b(?:Vessel|Process for|update summary for) (.+? V\.\w+)")


def place(name: str) -> str:
    """CALLAO_PERU or "VALPARAISO, CHILE" as "Callao, Peru". A short country such as UAE or
    US is a code, so it stays in capitals; a short word in a port name (JEBEL ALI) is not."""
    parts = [p for p in re.split(r"\s*[_,]\s*", name.strip()) if p]
    return ", ".join(p if i == len(parts) - 1 and i and len(p) <= 3 else " ".join(w.capitalize() for w in p.split())
                     for i, p in enumerate(parts))


def shipment(subject: str, body: str) -> list[str]:
    """[customer, destination] when the email names them, else the vessel or the order."""
    if other := DRAFT_BL_VESSEL.match(subject) or PO.match(subject):
        return [other.group(1)]
    who = where = None
    found = DASHED.match(subject) or UNDERSCORED.match(subject)
    if found:
        where, who = found.group(1), found.group(2).strip()
    elif si := SI_SUBJECT.match(subject):
        where = si.group(1)
    if who is None and (c := CONSIGNEE.search(body)):
        who = c.group(1).strip()
    if where is None and (p := POD.search(body)):
        where = p.group(1)
    return [part for part in (who, place(where) if where else None) if part]


def about(intent: str | None, subject: str, body: str) -> list[str]:
    """The words a title needs after its label, copied from the email. Invoice and general
    emails are read from the body only: in this corpus their subjects often belong to
    another thread (a D&D charge under "RAK BILLING ... MISSING GR")."""
    subject, body = subject or "", body or ""
    if intent in ("check_draft_bl", "chase_draft_bl", "resend_documents", "submit_si"):
        return shipment(subject, body)
    if intent in ("cancel_invoice", "missing_gr", "charge_query"):
        number, customer = INVOICE_NO.search(body), CANCEL_FOR.search(body)
        return [m.group(1) for m in (number, customer) if m]
    if intent == "dd_charges":
        found = CHARGES_FOR.search(body)
        return [found.group(1)] if found else []
    if intent in ("system_notice", "schedule_update"):
        found = VESSEL.search(body)
        return [found.group(1)] if found else []
    return []
