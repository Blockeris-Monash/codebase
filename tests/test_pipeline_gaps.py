"""The pipeline gaps from #147 B3: shapes of real mail the dataset never had.

None of these changes a result on the provided dataset (the mutation check, the
rules-first check and results.js guard that); each is a case a live mailbox or an
upload would meet.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from backend import app as app_module
from backend.compare.comparator import compare
from backend.compare.normalise import compare_row, normalise
from backend.contracts import FIELD_NAMES
from backend.extract.rules import comparison_result
from backend.read.documents import _pdf_pairs, read_txt
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


# --- B3.4 ------------------------------------------------------------------

@pytest.mark.parametrize("si, bl, verdict", [
    ("1×20GP + 1×40HC", "1×20GP + 2×40HC", "mismatch"),   # only the first number was compared
    ("1 x 20GP + 1 x 40HC", "1 x 40HC + 1 x 20GP", "match"),
    ("2 x 40HC", "1 x 20GP + 1 x 40HC", "mismatch"),
    ("2 x 40'HC", "2 X 40HC", "match"),
    ("2", "2 x 40HC", "match"),                            # no breakdown on one side: the total decides
    ("1 x 20GP + 1 x 40HC", "2", "match"),
    ("3 x 40HC", "2 x 40HC", "mismatch"),
])
def test_containers_are_counted_per_size(si: str, bl: str, verdict: str) -> None:
    production = compare("email_900", document("SI", container_count=si), document("BL", container_count=bl))
    reference = compare_row("container_count", si, bl)

    assert production.rows[5].verdict == verdict
    assert reference["verdict"] == verdict


# --- B3.8 ------------------------------------------------------------------

def cleaned(doc: dict) -> dict:
    return {**doc, "fields": app_module.apply_cleaner(doc["fields"])}


def every_path(field: str, si: dict, bl: dict) -> set[str]:
    """The verdicts for `field` from the service (cleaned, as /process-email runs it), the
    comparator on raw values alone, and the reference path: one value when they agree."""
    si_doc, bl_doc = document("SI", **si), document("BL", **bl)
    service = compare("email_900", cleaned(si_doc), cleaned(bl_doc))
    raw_only = compare("email_900", document("SI", **si), document("BL", **bl))
    reference = comparison_result("email_900", document("SI", **si), document("BL", **bl))
    return {next(r.verdict for r in service.rows if r.field == field),
            next(r.verdict for r in raw_only.rows if r.field == field),
            next(r["verdict"] for r in reference["rows"] if r["field"] == field)}


@pytest.mark.parametrize("si, bl, verdict", [
    ({"notify_party": "SAME AS CONSIGNEE", "consignee": "MOORIM SP CO., LTD"},
     {"notify_party": "MOORIM SP CO., LTD", "consignee": "MOORIM SP CO., LTD"}, "match"),
    ({"notify_party": "Same as Cnee.", "consignee": "MOORIM SP CO., LTD"},
     {"notify_party": "MOORIM SP CO., LTD", "consignee": "MOORIM SP CO., LTD"}, "match"),
    ({"notify_party": "SAME AS CONSIGNEE", "consignee": "MOORIM SP CO., LTD"},
     {"notify_party": "UAB NOVAKOPA", "consignee": "MOORIM SP CO., LTD"}, "mismatch"),
])
def test_same_as_consignee_means_that_documents_consignee(si: dict, bl: dict, verdict: str) -> None:
    assert every_path("notify_party", si, bl) == {verdict}


def test_same_as_consignee_is_still_shown_as_written() -> None:
    production = compare("email_900", document("SI", notify_party="SAME AS CONSIGNEE", consignee="ACME"),
                         document("BL", notify_party="ACME", consignee="ACME"))

    assert production.rows[2].si_raw == "SAME AS CONSIGNEE"


@pytest.mark.parametrize("si, bl, verdict", [
    ("TO THE ORDER OF MAYBANK BERHAD", "TO ORDER OF MAYBANK BERHAD", "match"),
    ("ORDER OF MAYBANK BERHAD", "To the order of Maybank Berhad", "match"),
    ("TO ORDER", "TO THE ORDER", "match"),
    ("TO ORDER", "TO ORDER OF MAYBANK BERHAD", "mismatch"),   # a negotiable BL to a bank is another instruction
    ("TO ORDER OF MAYBANK BERHAD", "TO ORDER OF CIMB BANK", "mismatch"),
])
def test_order_wording_is_one_form(si: str, bl: str, verdict: str) -> None:
    assert every_path("consignee", {"consignee": si}, {"consignee": bl}) == {verdict}


# --- B3.2 ------------------------------------------------------------------

def txt_pairs(tmp_path: Path, text: str) -> dict[str, str]:
    path = tmp_path / "doc.txt"
    path.write_text(text, encoding="utf-8")
    return dict(read_txt(path))


def test_a_txt_value_on_the_line_below_its_label_is_read(tmp_path: Path) -> None:
    """Consignee: with the name beneath it was ("Consignee", ""), a blank on a filled field."""
    pairs = txt_pairs(tmp_path, "Consignee:\nMOORIM SP CO., LTD\n\nVessel: X\n")

    assert pairs["Consignee"] == "MOORIM SP CO., LTD"
    assert pairs["Vessel"] == "X"


def test_an_indented_line_continues_the_value_above(tmp_path: Path) -> None:
    pairs = txt_pairs(tmp_path, "Shipper: APRIL FAR EAST (M) SDN BHD\n  TOWER 2, AVENUE 5\nNotify: UAB NOVAKOPA\n")

    assert pairs["Shipper"] == "APRIL FAR EAST (M) SDN BHD\nTOWER 2, AVENUE 5"
    assert pairs["Notify"] == "UAB NOVAKOPA"


def test_an_unindented_line_after_a_filled_value_is_not_absorbed(tmp_path: Path) -> None:
    """Free text under Gross Weight must not reach the weight parser."""
    pairs = txt_pairs(tmp_path, "Gross Weight: 21,577 KG\nSAY TWENTY ONE THOUSAND KG ONLY\n")

    assert pairs["Gross Weight"] == "21,577 KG"


def test_a_pdf_label_with_a_trailing_colon_takes_the_lines_beneath() -> None:
    pairs = dict(_pdf_pairs(["Consignee:", "MOORIM SP CO., LTD", "656, GANGNAM-DAERO", "Notify Party", "UAB NOVAKOPA"]))

    assert pairs["Consignee"] == "MOORIM SP CO., LTD | 656, GANGNAM-DAERO"
    assert pairs["Notify Party"] == "UAB NOVAKOPA"


def test_a_name_ends_at_its_line_break_on_the_reference_path() -> None:
    """Whitespace was collapsed before the split, so the address was glued onto the name."""
    assert normalise("shipper", "APRIL FAR EAST (M) SDN BHD\nTOWER 2, AVENUE 5") == "APRIL FAR EAST (M) SDN BHD"
    assert normalise("port_of_loading", "PORT KLANG\nMMSS 2507") == "PORT KLANG"
