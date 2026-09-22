"""The sentence a reviewer reads when a comparison could not be completed.

Contract 4 describes `evidence` as "one line naming what happened. Goes on
screen next to the confirm/correct action." Naming the category is not naming
what happened: "missing value" does not tell a reviewer whether a value is
coming (`TBA`) or a form was never filled (`_______`), and "could not be
confirmed as SI and BL" does not say that the file declares itself a packing
list. Both facts are in hand when the escalation is built and were being thrown
away.

Two stages produce contract 4 - the reference implementation in
`backend/extract/rules.py` and the production comparator in
`backend/compare/comparator.py`. The phrasing lives here so they cannot drift
into two sentences for one fact.
"""
from __future__ import annotations

SI = "SI"
BL = "BL"

# A pasted address in a blank field would otherwise run the sentence off the screen.
MAX_VALUE_CHARS = 40
# Naming every one of seven fields produces a line nobody reads.
MAX_FIELDS_NAMED = 3

BLANK = "is blank"
BOTH_SIDES = f"{SI} and the {BL}"


def describe_value(raw: str | None) -> str:
    """How a blank presented itself: the token it used, or that there was nothing."""
    text = (raw or "").strip()
    if not text:
        return BLANK
    if len(text) > MAX_VALUE_CHARS:
        text = text[:MAX_VALUE_CHARS - 1] + "…"
    return f'reads "{text}"'


def _one_blank(field: str, si_raw: str | None, bl_raw: str | None,
               si_absent: bool, bl_absent: bool) -> str:
    if si_absent and bl_absent:
        return f"{field} {BLANK} on the {BOTH_SIDES}"
    side, raw = (SI, si_raw) if si_absent else (BL, bl_raw)
    return f"{field} {describe_value(raw)} on the {side}"


def describe_blanks(blanks: list[tuple[str, str | None, str | None, bool, bool]]) -> str:
    """One line for the fields that had no comparable value.

    Each entry is (field, si_raw, bl_raw, si_absent, bl_absent). Naming the
    token is the point: `TBA` means a value is coming and someone should be
    chased, `_______` means a form went out unfilled, and the two want
    different replies.
    """
    if not blanks:  # the caller only reaches here with at least one, but a
        return "Missing value."  # sentence is cheaper than an IndexError later
    named = [_one_blank(*entry) for entry in blanks[:MAX_FIELDS_NAMED]]
    rest = len(blanks) - len(named)
    tail = f", and {rest} more" if rest else ""
    return f"Missing value: {'; '.join(named)}{tail}."


def describe_wrong_doc(si_declared: str | None, bl_declared: str | None) -> str:
    """One line for a file that is not the document it was sent as.

    `detect_doc_type` returns the document's own declared title when it is
    neither an SI nor a BL, so the real type is already known here.
    """
    wrong = [(SI, si_declared), (BL, bl_declared)]
    wrong = [(side, declared) for side, declared in wrong if declared != side]
    named = [f'the file sent as the {side} declares itself "{declared}"'
             for side, declared in wrong if declared]
    unnamed = [f"the file sent as the {side} declares no recognisable type"
               for side, declared in wrong if not declared]
    parts = named + unnamed
    if not parts:  # both look right; the caller should not have escalated
        return "Document type error: attached files could not be confirmed as SI and BL."
    return f"Document type error: {'; '.join(parts)}."


def describe_unreadable(si_status: str | None, bl_status: str | None) -> str:
    """One line for a file that would not open, naming which one and how it failed."""
    failed = [(side, status) for side, status in ((SI, si_status), (BL, bl_status))
              if status != "ok"]
    if not failed:
        return "Unreadable document: extraction stage could not parse document contents."
    parts = [f"the {side} could not be read ({status or 'no status given'})"
             for side, status in failed]
    return f"Unreadable document: {'; '.join(parts)}."
