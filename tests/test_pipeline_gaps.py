"""The pipeline gaps from #147 B3: shapes of real mail the dataset never had.

None of these changes a result on the provided dataset (the mutation check, the
rules-first check and results.js guard that); each is a case a live mailbox or an
upload would meet.
"""
from __future__ import annotations

import pytest

from backend import app as app_module
from backend.compare.comparator import compare
from backend.compare.normalise import normalise
from backend.contracts import FIELD_NAMES
from backend.read.labels import detect_doc_type


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


# --- B3.6 ------------------------------------------------------------------

@pytest.mark.parametrize("title, role", [
    ("SHIPPING INSTRUCTIONS", "SI"),
    ("Shipping Instruction - Booking 5RSG-00133", "SI"),
    ("BL INSTRUCTIONS", "SI"),
    ("BILL OF LADING INSTRUCTION", "SI"),
    ("DRAFT BILL OF LADING", "BL"),
    ("SEA WAYBILL", "BL"),
    ("SEAWAYBILL (DRAFT)", "BL"),
    ("NON-NEGOTIABLE BILL OF LADING", "BL"),
    ("Bill of Lading (Draft)", "BL"),
    ("B/L DRAFT", "BL"),
])
def test_a_title_is_recognised_by_its_wording_not_one_exact_line(title: str, role: str) -> None:
    """Only the dataset's exact first lines were known, so real titles read as the wrong document."""
    assert detect_doc_type(title) == role


@pytest.mark.parametrize("title", ["COMMERCIAL INVOICE", "PACKING LIST", "CERTIFICATE OF ORIGIN", "BILL OF EXCHANGE"])
def test_another_document_still_names_itself(title: str) -> None:
    assert detect_doc_type(title) == title


# --- B3.5 ------------------------------------------------------------------

@pytest.mark.parametrize("written, kilograms", [
    ("21.577,00 KG", 21577.0),      # European: dots group thousands, the comma is the decimal point
    ("1.234.567 KGS", 1234567.0),
    ("21 577,5 KG", 21577.5),
    ("40,326 KG", 40326.0),         # the dataset's own forms read as before
    ("40,326.5 KG", 40326.5),
    ("12.5 MT", 12500.0),
    ("21.577 KG", 21.577),          # a lone dot group is ambiguous; today's reading is kept
])
def test_a_weight_is_read_the_way_its_separators_say(written: str, kilograms: float) -> None:
    assert float(app_module.clean_weight(written)) == pytest.approx(kilograms)
    assert float(normalise("gross_weight_kg", written.removesuffix(" MT"))) == pytest.approx(
        kilograms / (1000 if written.endswith("MT") else 1))
