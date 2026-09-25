"""The pipeline gaps from #147 B3: shapes of real mail the dataset never had.

None of these changes a result on the provided dataset (the mutation check, the
rules-first check and results.js guard that); each is a case a live mailbox or an
upload would meet.
"""
from __future__ import annotations

import pytest

from backend import app as app_module
from backend.compare.comparator import compare
from backend.contracts import FIELD_NAMES


def document(role: str, **raws: str | None) -> dict:
    """A readable extract whose fields all match the other side's, except those given."""
    fields = {name: {"present": True, "label_seen": name, "raw": f"SAME {name.upper()}"} for name in FIELD_NAMES}
    fields["container_count"]["raw"] = "2 x 40HC"
    fields["gross_weight_kg"]["raw"] = "40,326 KG"
    for name, raw in raws.items():
        fields[name] = {"present": raw is not None, "label_seen": name, "raw": raw}
    return {"email_id": "email_900", "declared_role": role, "detected_doc_type": role,
            "parse_status": "ok", "fields": fields}


# --- B3.9 ------------------------------------------------------------------

def test_a_null_field_escalates_instead_of_crashing() -> None:
    si = document("SI")
    si["fields"]["consignee"] = None

    result = compare("email_900", si, document("BL"))

    assert (result.status, result.review_reason) == ("NEEDS_REVIEW", "missing_value")


def test_null_fields_escalate_instead_of_crashing() -> None:
    si = {**document("SI"), "fields": None}

    result = compare("email_900", si, document("BL"))

    assert (result.status, result.review_reason) == ("NEEDS_REVIEW", "missing_value")


def test_the_cleaner_treats_a_null_field_as_absent() -> None:
    cleaned = app_module.apply_cleaner({**document("SI")["fields"], "consignee": None})

    assert cleaned["consignee"]["norm"] is None


def test_the_cleaner_treats_null_fields_as_all_absent() -> None:
    assert all(field["norm"] is None for field in app_module.apply_cleaner(None).values())


# --- B3.11 -----------------------------------------------------------------

def test_the_startup_line_does_not_claim_vision_the_service_never_uses(monkeypatch, caplog) -> None:
    """Nothing in the service calls read_scan, yet SHIP_HAPPENS_VISION=1 printed vision=on."""
    monkeypatch.setenv("SHIP_HAPPENS_VISION", "1")

    with caplog.at_level("INFO", logger="backend.app"):
        app_module.say_what_is_switched_on()

    said = [record for record in caplog.records if record.name == "backend.app"]
    assert not any("vision=" in record.getMessage() for record in said)
    assert any(record.levelname == "WARNING" and "SHIP_HAPPENS_VISION" in record.getMessage() for record in said)


def test_the_startup_line_stays_quiet_about_vision_when_it_is_not_asked_for(monkeypatch, caplog) -> None:
    monkeypatch.delenv("SHIP_HAPPENS_VISION", raising=False)

    with caplog.at_level("INFO", logger="backend.app"):
        app_module.say_what_is_switched_on()

    assert not any("SHIP_HAPPENS_VISION" in record.getMessage() for record in caplog.records)
