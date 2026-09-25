"""The labels already say what the seven fields are, on most documents.

`backend/extract/rules.py` aligns the reader's (label, value) pairs onto the
seven field names with no network and no model. It was used in tests and nowhere
in the serving path, so every document paid for a model call - including the
hundreds whose label wording has been parsed since the first day.

Measured on the 250-file corpus before this landed: 237 documents give all seven
fields by rule at about 1 ms each, and over the 124 comparison emails the verdict
is identical to the model's every single time. What the model call was buying on
those documents was latency.

The guard that makes this safe is that it is all-or-nothing. A partial answer is
worse than none: the comparator reads a missing field as something a person must
look at, so six of seven fields would turn "not read yet" into "this document
does not state a consignee".
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from backend.app import extract_by_rule, extract_document, rules_first_enabled
from backend.compare.comparator import compare
from backend.contracts import FIELD_NAMES, ParseStatusType
from backend.extract.rules import attachment_meta, document_extract

ROOT = Path(__file__).resolve().parents[1]
EXTRACTS = ROOT / "results" / "extracts"

COMPLETE = [("Shipper", "ACME LTD"), ("Consignee", "BETA PTE LTD"),
            ("Notify Party", "BETA PTE LTD"), ("Port of Loading", "PORT KLANG, MALAYSIA"),
            ("Port of Discharge", "JEBEL ALI, UAE"), ("Containers", "3 x 40'HC"),
            ("Gross Weight", "54,120 KG")]


def test_a_complete_document_never_reaches_the_model() -> None:
    result = extract_by_rule("email_001", "SI", COMPLETE, "SHIPPING INSTRUCTION",
                             ParseStatusType.Ok)

    assert result is not None
    assert all(f["present"] for f in result["fields"].values())
    assert result["detected_doc_type"] == "SI"


@pytest.mark.parametrize("drop", FIELD_NAMES[:3])
def test_one_missing_field_falls_through_to_the_model(drop: str) -> None:
    """All-or-nothing. Six of seven is not a cheaper answer, it is a different
    and wrong one, because the comparator escalates on a missing field."""
    label = {"shipper": "Shipper", "consignee": "Consignee",
             "notify_party": "Notify Party"}[drop]
    partial = [pair for pair in COMPLETE if pair[0] != label]

    assert extract_by_rule("email_001", "SI", partial, "SHIPPING INSTRUCTION",
                           ParseStatusType.Ok) is None


def test_a_document_that_did_not_open_is_not_read_by_rule() -> None:
    """An unreadable file has no pairs to align, and claiming otherwise would
    hide the escalation the reader correctly produced."""
    assert extract_by_rule("email_511", "BL", [], None, ParseStatusType.Unreadable) is None


def test_the_switch_turns_it_off(monkeypatch) -> None:
    """During judging the way to undo this is an environment variable and a
    restart, so the value is read per call rather than captured at import."""
    from backend import app

    monkeypatch.setenv(app.RULES_FIRST, "0")

    assert rules_first_enabled() is False
    assert extract_by_rule("email_001", "SI", COMPLETE, "SHIPPING INSTRUCTION",
                           ParseStatusType.Ok) is None


def test_it_is_on_by_default(monkeypatch) -> None:
    from backend import app

    monkeypatch.delenv(app.RULES_FIRST, raising=False)

    assert rules_first_enabled() is True


def test_the_cache_still_wins_over_the_rules() -> None:
    """The saved extracts are the measured, submitted answers. A rule that
    disagreed with one would silently change a published number."""
    cached = asyncio.run(extract_document("email_001", "SI", COMPLETE,
                                          "SHIPPING INSTRUCTION", ParseStatusType.Ok))
    saved = json.loads((EXTRACTS / "email_001_SI.json").read_text(encoding="utf-8"))

    assert cached["fields"] == saved["fields"]


def test_the_rules_path_reaches_the_same_verdict_on_every_comparison_email(
        data_dir: Path) -> None:
    """The one that matters. Same comparator, two extractors, every comparison
    email in the corpus: the status, the escalation reason and the exact defect
    set have to match, or this trades a measured result for a faster wrong one.

    This is also the guard against a later change to `read/labels.py` quietly
    pulling the two paths apart.
    """
    disagreements = []
    compared = 0

    for record in sorted((data_dir / "inbox").glob("email_*.json")):
        email = json.loads(record.read_text(encoding="utf-8"))
        attachments = email.get("attachments") or []
        if len(attachments) < 2:
            continue

        metas = {}
        for attachment in attachments:
            meta = attachment_meta(str(attachment))
            metas[meta["declared_role"]] = meta
        if set(metas) != {"SI", "BL"}:
            continue

        model = {}
        for role, meta in metas.items():
            saved = EXTRACTS / f"{Path(meta['path']).stem}.json"
            if saved.exists():
                model[role] = json.loads(saved.read_text(encoding="utf-8"))
        if len(model) != 2:
            continue

        by_rule = {role: document_extract(str(data_dir), email["email_id"], meta)
                   for role, meta in metas.items()}

        theirs = compare(email["email_id"], model["SI"], model["BL"])
        ours = compare(email["email_id"], by_rule["SI"], by_rule["BL"])
        key = lambda r: (r.status, r.review_reason, tuple(sorted(r.defect_fields)))
        compared += 1
        if key(theirs) != key(ours):
            disagreements.append(f"{email['email_id']}: model={key(theirs)} rules={key(ours)}")

    assert compared >= 120, f"only {compared} emails compared, the corpus should give ~124"
    assert disagreements == []
