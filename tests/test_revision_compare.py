"""D1: a revised draft BL is labelled field by field against the draft before it (#147 D1).

Each field is fixed, still wrong, a new mistake or unchanged, from the SI checked against
each draft. The verdict is still the latest draft against the SI; the labels are evidence
beside it.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from backend import app as app_module
from backend.classify import EmailInput
from backend.compare.comparator import compare, revision_between
from backend.contracts import FIELD_NAMES
from cli.validate_contracts import load_contract, validate
from tests.js_runner import page_function, run_node

EDGE = Path(__file__).resolve().parent / "edge_cases"


def document(role: str, **raws: str) -> dict:
    fields = {name: {"present": True, "label_seen": name, "raw": f"SAME {name.upper()}"} for name in FIELD_NAMES}
    fields["container_count"]["raw"], fields["gross_weight_kg"]["raw"] = "2 x 40HC", "40,326 KG"
    for name, raw in raws.items():
        fields[name] = {"present": True, "label_seen": name, "raw": raw}
    return {"email_id": "email_900", "declared_role": role, "detected_doc_type": role,
            "parse_status": "ok", "fields": fields}


def labels(v1: dict, v2: dict) -> dict[str, str]:
    si = document("SI")
    revision = revision_between(compare("email_900", si, v1), compare("email_900", si, v2), "v1.txt", "v2.txt")
    return {row.field: row.label for row in revision.rows}


@pytest.mark.parametrize("v1, v2, label", [
    ({"consignee": "WRONG CO"}, {}, "fixed"),
    ({"consignee": "WRONG CO"}, {"consignee": "STILL WRONG CO"}, "still_wrong"),
    ({}, {"consignee": "WRONG CO"}, "new_mistake"),
    ({}, {}, "unchanged"),
])
def test_each_label_follows_from_the_two_verdicts(v1: dict, v2: dict, label: str) -> None:
    assert labels(document("BL", **v1), document("BL", **v2))["consignee"] == label


def test_a_defect_planted_in_the_revision_only_is_a_new_mistake() -> None:
    """Mutation check: the revision must never hide what it broke."""
    assert labels(document("BL"), document("BL", gross_weight_kg="40,376 KG"))["gross_weight_kg"] == "new_mistake"


def test_a_defect_planted_in_the_first_draft_only_is_fixed() -> None:
    assert labels(document("BL", container_count="3 x 40HC"), document("BL"))["container_count"] == "fixed"


def test_the_revised_edge_case_says_the_consignee_was_fixed(monkeypatch) -> None:
    monkeypatch.setattr(app_module, "DATA_DIR", EDGE)
    email = EmailInput(**json.loads((EDGE / "inbox" / "email_908.json").read_text(encoding="utf-8")))

    result = asyncio.run(app_module.compare_email(email))

    assert result.status == "OK"
    assert result.revision.previous == "email_908_BL.txt" and result.revision.current == "email_908_BL_REVISED.txt"
    assert {r.field: r.label for r in result.revision.rows}["consignee"] == "fixed"
    assert {r.label for r in result.revision.rows if r.field != "consignee"} == {"unchanged"}
    assert validate(json.loads(result.model_dump_json()), load_contract("ComparisonResult"), "04", []) == []


def test_an_unreadable_first_draft_is_said_and_not_labelled() -> None:
    si, v1 = document("SI"), {**document("BL"), "parse_status": "unreadable"}

    revision = revision_between(compare("email_900", si, v1), compare("email_900", si, document("BL")), "v1.pdf", "v2.txt")

    assert revision.previous_readable is False and revision.rows == []


def test_one_bl_carries_no_revision_block() -> None:
    assert compare("email_900", document("SI"), document("BL")).revision is None


STRIP = f"""
const FIELDS = {{consignee: "Consignee", gross_weight_kg: "Gross weight", shipper: "Shipper"}};
const T = s => s, t = (s, vars) => vars ? s.replace(/\\{{(\\w+)\\}}/g, (_, k) => vars[k]) : s, fld = f => FIELDS[f];
const esc = s => String(s);
const REVISION_SHOWN = [["fixed", "Fixed"], ["still_wrong", "Still wrong"], ["new_mistake", "New mistake"]];
{page_function("revisionHTML")}
"""


def test_the_page_lists_what_the_revision_fixed_and_broke() -> None:
    html = run_node(STRIP + """
        console.log(JSON.stringify(revisionHTML({revision: {previous: "v1.txt", current: "v2.txt", previous_readable: true,
            rows: [{field: "consignee", label: "fixed"}, {field: "gross_weight_kg", label: "new_mistake"},
                   {field: "shipper", label: "unchanged"}]}})));
    """)

    assert "Fixed:</b> Consignee" in html and "New mistake:</b> Gross weight" in html
    assert "Shipper" not in html and "v2.txt against v1.txt" in html


def test_an_email_with_one_bl_shows_no_strip() -> None:
    assert run_node(STRIP + "console.log(JSON.stringify(revisionHTML({})));") == ""
