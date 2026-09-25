"""Sample reply drafts for the demo account's invoice and general emails.

Live mail is drafted by the AI (backend/reply.py). The demo account calls no model, so these
were written by hand for the demo (by Claude, on 25 Sep): one per kind of email, filled in
from the email itself (backend/intent.py gives the kind and the words it is about). They are
not Ship Happens' output, and the page labels every one as a sample.

Like the live drafter, a sample never states a charge, a total or a date the email did not
give: it acknowledges the request and says what happens next.
"""
from __future__ import annotations

import re

SIGN_OFF = "\n\nBest regards,\nGlobeTrans Support Team"

# {0} and {1} are the email's own words from backend/intent.py about(): the invoice number
# and customer, the D&D reference, or the vessel.
SAMPLES = {
    "cancel_invoice": ("Thank you for your request to cancel invoice {0} for {1} and reverse the PGI "
                       "following the booking amendment.\n\nWe are processing the cancellation and the "
                       "reversal now, and will confirm once both are done."),
    "charge_query": ("Thank you for your query on invoice {0}.\n\nWe are checking whether the THC and "
                     "local charges are included or billed separately, and will send you the breakdown "
                     "as soon as we have it."),
    "missing_gr": ("Thank you for letting us know that the GR is still missing for invoice {0}.\n\n"
                   "We are arranging for the GR to be posted and will confirm once it is done, so "
                   "billing can proceed."),
    "dd_charges": ("Thank you for sending the D&D / detention charges for {0}.\n\nWe are checking the "
                   "amount against our records and will confirm it before you release payment."),
    "schedule_update": ("Thank you for the update on {0}.\n\nNoted. We will follow up on the documents "
                        "on our side."),
    "outstanding_reminder": ("Thank you for the reminder and the list of outstanding items.\n\nWe are "
                             "working through the pending items and will update you on each one."),
    "office_notice": "Thank you, and a happy New Year to you and the team as well.",
}

# Who signs off after these words, in these emails.
SIGNED = re.compile(r"(?:Best Regards|Warm regards|Regards|Thank you),?[ \t]*\n\s*([^\n]+)", re.I)
# A sign-off that names a department rather than a person.
DEPARTMENT = re.compile(r"\b(?:Documentation|Operations|Management|Team)\b", re.I)


def sender_name(body: str) -> str | None:
    """The full name the sender signed with (names here are written in several orders, so
    the whole name is safer than a guessed first name), or None for a department or none."""
    found = SIGNED.search(body or "")
    if not found or DEPARTMENT.search(found.group(1)):
        return None
    return found.group(1).strip()


def sample_reply(intent: str | None, about: list[str], body: str) -> str | None:
    """The sample draft for one demo email, or None when there is none for its kind."""
    if intent not in SAMPLES:
        return None
    text = SAMPLES[intent].format(*about, *[""] * 2)
    return f"Dear {sender_name(body) or 'Team'},\n\n{text}{SIGN_OFF}"
