"""End to end — an email goes in, a contract-shaped record comes out."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.contracts import FIELD_NAMES, ReviewReasonType, StatusType
from backend.read.labels import canonical_field
from cli.make_fixtures import build, classify_from_body, load_scenarios
from backend.compare.normalise import compare_row, normalise
from backend.read.documents import read_document
from cli.validate_contracts import load_contract, validate

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"

# Each row is a real email and the verdict the documents support.
EXPECTED_OUTCOMES = [
    ("email_064", StatusType.Ok, None, []),
    ("email_025", StatusType.Mismatch, None, ["port_of_discharge", "container_count"]),
    ("email_004", StatusType.Mismatch, None, ["consignee", "notify_party"]),
    ("email_501", StatusType.NeedsReview, ReviewReasonType.WrongDocType, []),
    ("email_506", StatusType.NeedsReview, ReviewReasonType.MissingAttachment, []),
    ("email_511", StatusType.NeedsReview, ReviewReasonType.Unreadable, []),
    ("email_516", StatusType.NeedsReview, ReviewReasonType.MissingValue, []),
    ("email_517", StatusType.NeedsReview, ReviewReasonType.MissingValue, []),
]


def load_email(data_dir: Path, email_id: str) -> dict[str, object]:
    return json.loads((data_dir / "inbox" / f"{email_id}.json").read_text(encoding="utf-8"))


# --- the eight outcomes -------------------------------------------------

@pytest.mark.parametrize("email_id,status,reason,defects", EXPECTED_OUTCOMES)
def test_email_reaches_the_expected_verdict(data_dir: Path, email_id: str,
                                            status: str, reason: str | None,
                                            defects: list[str]) -> None:
    _, _, comparison = build(str(data_dir), load_email(data_dir, email_id))

    assert comparison["status"] == status
    assert comparison["review_reason"] == reason
    assert sorted(comparison["defect_fields"]) == sorted(defects)


def test_defect_fields_are_an_exact_set_not_a_superset(data_dir: Path) -> None:
    """End-to-end credit needs the exact set. Flagging a sixth field on top
    of the right two scores zero, so over-flagging is as bad as missing."""
    _, _, comparison = build(str(data_dir), load_email(data_dir, "email_025"))

    assert set(comparison["defect_fields"]) == {"port_of_discharge", "container_count"}


def test_escalation_carries_evidence_a_human_can_act_on(data_dir: Path) -> None:
    """The brief requires escalating with the reason and the context, not
    just a flag."""
    _, _, comparison = build(str(data_dir), load_email(data_dir, "email_501"))

    assert "COMMERCIAL INVOICE" in comparison["evidence"]


# --- the ordering that produces false alarms if reversed ----------------

def test_absent_value_escalates_instead_of_reporting_a_defect(data_dir: Path) -> None:
    """email_516's SI gross weight is 'N/A'. Compare before checking and it
    reports a weight mismatch that is not real."""
    _, _, comparison = build(str(data_dir), load_email(data_dir, "email_516"))

    assert comparison["status"] == StatusType.NeedsReview
    assert comparison["defect_fields"] == []


def test_a_missing_locode_is_not_a_defect(data_dir: Path) -> None:
    """Same email: the SI port lacks the code the BL carries. That is
    formatting, not a discrepancy."""
    _, _, comparison = build(str(data_dir), load_email(data_dir, "email_516"))
    port_row = next(r for r in comparison["rows"] if r["field"] == "port_of_loading")

    assert port_row["verdict"] == "match"


# --- normalisation rules, each with the case that justifies it ----------

@pytest.mark.parametrize("field,si_raw,bl_raw,verdict", [
    # The UN/LOCODE is identical on both sides of every planted port defect.
    ("port_of_discharge", "MOMBASA, KENYA (KEMBA)", "TUTICORIN, INDIA (KEMBA)", "mismatch"),
    ("port_of_loading", "NHAVA SHEVA, INDIA (INNSA)", "BUATAN, INDONESIA (INNSA)", "mismatch"),
    # A code present on one side only is formatting.
    ("port_of_loading", "SINGAPORE", "SINGAPORE (SGSIN)", "match"),
    # A non-locode parenthetical must survive.
    ("port_of_loading", "PORT KLANG (WESTPORT), MALAYSIA (MYPKG)",
     "PORT KLANG (WESTPORT), MALAYSIA", "match"),
    # Count is the discriminator; the equipment type never varies alone.
    ("container_count", "6 x 20'GP", "5 x 20'GP", "mismatch"),
    ("container_count", "15 x 20'FCL", "15 x 20'FCL", "match"),
    # Separators and units differ across formats; the number does not.
    ("gross_weight_kg", "243,588 KG", "243588", "match"),
    ("gross_weight_kg", "323,250 KG", "322,250 KG", "mismatch"),
    # Two different legal entities. Suffix stripping would merge them.
    ("shipper", "APRIL FINE PAPER TRADING",
     "APRIL FINE PAPER TRADING (MIDDLE EAST) FZE", "mismatch"),
    # Name only - the address block must not dilute the comparison.
    ("consignee", "AL GURG STATIONERY LLC | P.O. BOX 5069",
     "AL GURG STATIONERY LLC | DIFFERENT ADDRESS", "match"),
])
def test_comparison_rule(field: str, si_raw: str, bl_raw: str, verdict: str) -> None:
    assert compare_row(field, si_raw, bl_raw)["verdict"] == verdict


@pytest.mark.parametrize("sentinel", ["N/A", "n/a", "TBA", "____MT", "_______ MTS", "", "  ", "-"])
def test_sentinel_values_have_no_comparable_form(sentinel: str) -> None:
    assert normalise("gross_weight_kg", sentinel) is None


# --- cross-format -------------------------------------------------------

def test_excel_si_against_word_bl_compares_cleanly(attachments: Path) -> None:
    """email_055 is the mixed-format case: nothing downstream should be able
    to tell the two documents came from different applications."""
    def fields(name: str) -> dict[str, str]:
        _, pairs = read_document(attachments / name)
        found: dict[str, str] = {}
        for label, value in pairs:
            field = canonical_field(label)
            if field is not None and field not in found:
                found[field] = value
        return found

    si, bl = fields("email_055_SI.xlsx"), fields("email_055_BL.docx")
    verdicts = [compare_row(f, si.get(f), bl.get(f))["verdict"] for f in FIELD_NAMES]

    assert verdicts == ["match"] * len(FIELD_NAMES)


# --- classification -----------------------------------------------------

@pytest.mark.parametrize("email_id,category", [
    ("email_064", "BL_COMPARISON"),
    ("email_025", "BL_COMPARISON"),
    ("email_506", "BL_COMPARISON"),   # a comparison with nothing attached
    ("email_007", "SI_REQUEST"),
    ("email_017", "INVOICE_QUERY"),
    ("email_012", "GENERAL"),
    ("email_015", "SPAM"),
])
def test_email_is_classified_from_its_body(data_dir: Path, email_id: str,
                                           category: str) -> None:
    matched, _ = classify_from_body(load_email(data_dir, email_id))

    assert matched == category


def test_evidence_quotes_text_that_really_appears(data_dir: Path) -> None:
    """The evidence string is shown to a human reviewer, so it has to be
    true of this email rather than a generic label."""
    email = load_email(data_dir, "email_025")
    _, evidence = classify_from_body(email)
    quoted = evidence.split("body contains: '")[1].rstrip("'")

    assert quoted.lower() in str(email["body"]).lower()


@pytest.mark.parametrize("email_id", ["email_501", "email_502", "email_503",
                                      "email_504", "email_505"])
def test_a_wrong_document_is_still_a_comparison_request(data_dir: Path,
                                                        email_id: str) -> None:
    """These attach an invoice, packing list or certificate in the BL slot.
    The sender believes they are sending a BL, so it is a comparison request
    that escalates - not a different category."""
    matched, _ = classify_from_body(load_email(data_dir, email_id))

    assert matched == "BL_COMPARISON"


def test_every_email_with_attachments_is_a_comparison(data_dir: Path) -> None:
    """Attachments are not the gate - 3 comparisons have none - but nothing
    that carries documents belongs to another category."""
    wrong = [p.stem for p in sorted((data_dir / "inbox").glob("email_*.json"))
             if json.loads(p.read_text(encoding="utf-8"))["attachments"]
             and classify_from_body(json.loads(p.read_text(encoding="utf-8")))[0] != "BL_COMPARISON"]

    assert wrong == []


def test_the_subject_line_alone_cannot_separate_the_categories(data_dir: Path) -> None:
    """email_001 has documents attached; email_003 asks someone else to send
    the draft BL. Same subject family, opposite intent."""
    with_docs, _ = classify_from_body(load_email(data_dir, "email_001"))
    without_docs, _ = classify_from_body(load_email(data_dir, "email_003"))

    assert with_docs != without_docs


# --- fixtures and contracts ---------------------------------------------

@pytest.mark.parametrize("path", sorted(FIXTURES.glob("[0-9][0-9]-*.json")),
                         ids=lambda p: p.stem)
def test_fixture_satisfies_every_contract_it_carries(path: Path) -> None:
    bundle = json.loads(path.read_text(encoding="utf-8"))
    errors: list[str] = []
    for key in ("EmailRecord", "ClassificationResult", "ComparisonResult", "SubmissionEntry"):
        if bundle.get(key) is not None:
            validate(bundle[key], load_contract(key), f"{path.name}:{key}", errors)

    assert errors == []


@pytest.mark.parametrize("path", sorted(FIXTURES.glob("[0-9][0-9]-*.json")),
                         ids=lambda p: p.stem)
def test_fixture_still_matches_what_the_pipeline_produces(data_dir: Path,
                                                          path: Path) -> None:
    """The regression guard. Change a rule and any fixture it moves fails
    here, instead of surfacing later as an unexplained score drop."""
    bundle = json.loads(path.read_text(encoding="utf-8"))
    _, _, comparison = build(str(data_dir), load_email(data_dir, bundle["_why"]["email_id"]))

    assert comparison == (bundle["ComparisonResult"] or comparison)


def test_every_scenario_has_a_fixture_on_disk() -> None:
    names = {p.stem.split("-", 1)[1] for p in FIXTURES.glob("[0-9][0-9]-*.json")}

    assert names == {s["name"] for s in load_scenarios()}


def test_every_review_reason_has_a_worked_example() -> None:
    """All four values in the schema need a fixture, or nothing exercises
    that branch."""
    reasons = set()
    for path in FIXTURES.glob("[0-9][0-9]-*.json"):
        comparison = json.loads(path.read_text(encoding="utf-8")).get("ComparisonResult")
        if comparison and comparison["review_reason"]:
            reasons.add(comparison["review_reason"])

    assert reasons == {r.value for r in ReviewReasonType}


def test_submission_sample_has_one_entry_per_fixture() -> None:
    submission = json.loads((FIXTURES / "SubmissionSample.json").read_text(encoding="utf-8"))

    assert len(submission) == len(load_scenarios())
