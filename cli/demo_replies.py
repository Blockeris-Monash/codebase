"""Reply drafts for the demo account's invoice and general emails.

Live mail is drafted by the AI (backend/reply.py) when the person presses Draft a reply. The
demo account calls no model, so each of these emails carries a draft written in advance by
Claude (on 25 Sep), one per email, from that email alone: cli/demo_drafts.json, keyed by
email id. The page shows it behind the same Draft a reply button, and says who wrote it.

Like the live drafter, a draft never states a charge, a total or a date the email did not
give: it acknowledges the request and says what happens next. The 15 automated notices have
none, since nobody replies to an automated sender.
"""
from __future__ import annotations

import json
from pathlib import Path

DRAFTS: dict[str, str] = json.loads((Path(__file__).with_name("demo_drafts.json")).read_text(encoding="utf-8"))


def demo_draft(email_id: str) -> str | None:
    """The draft written for one demo email, or None when it has none."""
    return DRAFTS.get(email_id)
