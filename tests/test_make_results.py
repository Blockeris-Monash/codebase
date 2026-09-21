"""cli.make_results: the UI's results file uses the team's real reader, extracts and comparator."""
from pathlib import Path

from cli.make_results import build_email, fallback_category

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
NO_CLASSIFICATIONS = ROOT / "results" / "no-such-classifications"


def build(email_id: str) -> dict:
    return build_email(DATA / "inbox" / f"{email_id}.json", DATA, NO_CLASSIFICATIONS)


def test_matching_pair_is_ok_with_seven_rows():
    email = build("email_064")
    assert email["category"] == "BL_COMPARISON"
    assert email["status"] == "OK"
    assert len(email["rows"]) == 7


def test_mismatch_flags_exactly_the_defect_fields():
    email = build("email_025")
    assert email["status"] == "MISMATCH"
    assert set(email["defect_fields"]) == {"port_of_discharge", "container_count"}


def test_comparison_email_carries_both_documents_for_the_ui_and_a_live_recheck():
    docs = build("email_025")["docs"]
    assert set(docs) == {"SI", "BL"}
    assert "Port of Discharge" in docs["SI"]["text"]
    assert docs["BL"]["pairs"] and docs["BL"]["title"]


def test_email_without_attachments_is_not_compared():
    email = build("email_003")
    assert "status" not in email
    assert email["decided_by"] == "fallback"


def test_fallback_is_marked_so_the_ui_never_calls_it_the_ai():
    assert build("email_003")["decided_by"] == "fallback"


def test_fallback_categories():
    assert fallback_category("Bitcoin investment opportunity", "", 0) == "SPAM"
    assert fallback_category("Request to cancel invoice", "", 0) == "INVOICE_QUERY"
    assert fallback_category("REQUEST SI", "please send the SI", 0) == "SI_REQUEST"
    assert fallback_category("Daily berthing report", "", 0) == "GENERAL"
    assert fallback_category("anything", "", 2) == "BL_COMPARISON"
