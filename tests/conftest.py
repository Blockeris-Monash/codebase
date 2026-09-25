"""Shared fixtures. The dataset lives outside the repo, so its location is
configurable and every test that needs it skips when it is absent."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

DEFAULT_DATA_DIR = REPO_ROOT / "data"
LIVE_OPT_IN = "SHIP_HAPPENS_LIVE"


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption("--data-dir", default=str(DEFAULT_DATA_DIR),
                     help="folder holding inbox/ and attachments/")


@pytest.fixture(scope="session")
def data_dir(request: pytest.FixtureRequest) -> Path:
    path = Path(request.config.getoption("--data-dir")).resolve()
    if not (path / "attachments").is_dir():
        pytest.skip(f"dataset not found at {path} - pass --data-dir")

    return path


@pytest.fixture(scope="session")
def attachments(data_dir: Path) -> Path:
    return data_dir / "attachments"


# backend/app.py calls load_dotenv() at import, so importing the service pulls a
# developer's .env into os.environ - including the model keys. The live gate stops
# *tests* calling a model; it cannot stop the *application* doing it, and the
# mailbox check classifies each new email in the background. So on any machine
# with a .env the suite made real model calls: 66.9s and a flaky failure against
# 1.45s and green with the keys cleared, a 45x difference, and quota spent on
# every run. CI never saw it because CI has no .env.
MODEL_KEYS = ("QWEN_API_KEY", "GOOGLE_API_KEY", "GEMINI_API_KEY", "GEMINI_CRITIC_API_KEY")


@pytest.fixture(autouse=True)
def no_model_calls_from_the_application(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the offline suite offline, whatever is in the developer's .env.

    Left alone when SHIP_HAPPENS_LIVE=1, because that is someone asking for the
    live tests by name and they need the keys.
    """
    if os.environ.get(LIVE_OPT_IN) == "1":
        return

    for name in MODEL_KEYS:
        monkeypatch.delenv(name, raising=False)


@pytest.fixture(autouse=True)
def no_reports_reach_the_real_queue(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tests make models fail on purpose, and each failure files a technical
    report. A developer's .env may hold the service key, so without this a test
    run would fill the team's admin queue with fake failures.

    Cleared through settings.SUPABASE_SECRET_NAMES rather than by name, so an
    alias added there later is covered here without anyone remembering to.
    """
    from backend.settings import SUPABASE_SECRET_NAMES

    for name in SUPABASE_SECRET_NAMES:
        monkeypatch.delenv(name, raising=False)


# --- verification report ------------------------------------------------
# Grouped by what each test actually proves, because "128 passed" tells a
# reader nothing about coverage. Matched against the test's node id, first
# match wins, so order matters.
REPORT_AREAS: list[tuple[str, str, str]] = [
    ("classification_critic", "Critic", "a second opinion only when there is a reason, and reported"),
    ("technical_report", "Technical reports", "every retry reaches the admin queue, most tries first"),
    ("vision", "Scans", "read the scans, and say what cannot be trusted"),
    ("sign_in_error", "Sign-in", "say why a sign-in did not finish"),
    ("vision", "Scans", "read the scans, refuse to guess at them"),
    ("phone_and_fold", "Any screen", "flip, fold, landscape and high contrast"),
    ("edge_case", "Edge cases", "real-world email shapes, expected result written first"),
    ("gmail_mailbox", "Live mailbox", "Gmail read into the pipeline, replies sent in the thread"),
    ("mailbox_email_id", "Edge cases", "real-world email shapes, expected result written first"),
    ("google_sign_in", "Sign in", "Google sign-in through Supabase"),
    ("review_state_store", "Saved state", "a mark survives a change of browser"),
    ("store", "Saved state", "a mark survives a change of browser"),
    ("reads_every_supported_format", "Formats", "txt, docx and xlsx parse"),
    ("locates_all_seven_fields", "Formats", "all 7 fields found in each format"),
    ("every_attachment_reads_except", "Formats", "242 of 250 parse"),
    ("pdf_form_layout_yields", "Formats", "PDF form layout, all 7 fields"),
    ("cannot_parse_says_so", "Formats", "scanned/corrupt PDFs escalate"),
    ("every_format_in_the_table", "Dispatch", "table and samples agree"),
    ("edi_reaches_all_seven", "EDI 304", "a different format, same 7 fields"),
    ("edi_goes_through_the_same", "EDI 304", "no special case in the pipeline"),
    ("304_declares_itself", "EDI 304", "ST segment carries the type"),
    ("edi_is_in_the_reader_table", "EDI 304", "one more dispatch entry"),
    ("port_is_the_code", "EDI 304", "port rule inverts vs documents"),
    ("port_qualifier_selects", "EDI 304", "R4 qualifier picks the field"),
    ("gross_weight_sums", "EDI 304", "sums lading lines"),
    ("net_weight_lines", "EDI 304", "net weight not counted as gross"),
    ("pounds_are_converted", "EDI 304", "pounds converted to kg"),
    ("omitted_trailing", "EDI 304", "short segments do not raise"),
    ("comments_and_line_breaks", "EDI 304", "interchange splitting"),
    ("delimiters_come_from_the_isa", "EDI 304", "delimiters read from ISA, not assumed"),
    ("same_data_parses_under_either", "EDI 304", "star/tilde and pipe/newline both work"),
    ("delimiters_fall_back", "EDI 304", "malformed header falls back"),
    ("both_pairs_and_a_title", "Dispatch", "one entry supplies both halves"),
    ("reads_every_email_in_the_folder", "Inbox", "every email in the bundle is read"),
    ("iterating_the_inbox", "Inbox", "iteration matches emails()"),
    ("fetches_one_email_by_id", "Inbox", "one email by id"),
    ("reads_an_attachment_as_text", "Inbox", "attachment bytes to text"),
    ("unreadable_bytes_do_not_raise", "Inbox", "undecodable bytes do not crash"),
    ("sample_submission_comes_from", "Inbox", "sample submission loads"),
    ("submitting_without_a_server", "Inbox", "submit without a server is refused, not silent"),
    ("trailing_slash", "Inbox", "trailing slash is the same inbox"),
    ("same_api_works_over_http", "Inbox", "identical API over HTTP"),
    ("submit_posts_the_submission", "Inbox", "submit posts and returns the scoreboard"),
    ("submit_sends_json", "Inbox", "submit sends parseable JSON"),
    ("real_bundle_holds_every_email", "Inbox", "all 520 emails present"),
    ("cached_pair_reports_both_seeded", "Orchestrator", "cached path finds both defects"),
    ("cached_clean_pair_is_ok", "Orchestrator", "a clean pair stays OK"),
    ("excel_si_against_word_bl", "Orchestrator", "xlsx SI vs docx BL align"),
    ("every_field_is_reported", "Orchestrator", "all 7 rows returned, not just defects"),
    ("cache_carries_the_parse_metadata", "Orchestrator", "cache keeps parse_status and doc type"),
    ("live_model_path_reaches", "Orchestrator", "live model agrees with the cache"),
    ("no_title_rather_than_raising", "Dispatch", "title fails like read_document"),
    ("absent_file", "Failure modes", "missing file escalates"),
    ("unsupported_extension", "Failure modes", "unknown format escalates"),
    ("corrupt_office_file", "Failure modes", "corrupt zip escalates, no crash"),
    ("near_empty_document", "Failure modes", "near-empty escalates"),
    ("no_attachment_in_the_corpus_raises", "Failure modes", "250 files, zero exceptions"),
    ("excel_si_against_word_bl", "Cross-format", "Excel SI vs Word BL, 7/7 match"),
    ("word_", "Office quirks", "Word <w:br/> splits name from address"),
    ("excel_", "Office quirks", "Excel shared strings resolved"),
    ("xml_entities", "Office quirks", "&amp; unescaped across formats"),
    ("label_variants", "Label alignment", "each shape of variation"),
    ("cjk_in_a_label", "Label alignment", "CJK stripped before lookup"),
    ("unrelated_labels", "Label alignment", "NET WEIGHT decoy not claimed"),
    ("document_type_comes_from_the_header", "Doc type", "header read, filename distrusted"),
    ("comparison_rule", "Comparison rules", "locode decoy, counts, weights, suffixes"),
    ("sentinel_values", "Comparison rules", "N/A, TBA, ____MT have no value"),
    ("absent_value_escalates", "Ordering", "sentinel checked before compare"),
    ("missing_locode_is_not_a_defect", "Ordering", "formatting is not a discrepancy"),
    ("email_reaches_the_expected_verdict", "End to end", "8 emails, 8 outcomes"),
    ("defect_fields_are_an_exact_set", "End to end", "exact set, no supersets"),
    ("escalation_carries_evidence", "End to end", "a human gets the reason"),
    ("classified_from_its_body", "Classification", "body decides, all 5 categories"),
    ("evidence_quotes_text", "Classification", "evidence is true of the email"),
    ("wrong_document_is_still", "Classification", "wrong doc type is still a comparison"),
    ("every_email_with_attachments", "Classification", "nothing with docs is miscategorised"),
    ("subject_line_alone", "Classification", "subject cannot separate intents"),
    ("both_comparators_agree", "Cross-check", "two comparators, same verdict, 126 emails"),
    ("escalation_reason_survives", "Cross-check", "same escalation reason on both paths"),
    ("corpus_has_the_expected", "Cross-check", "126 comparison emails"),
    ("fixture_satisfies_every_contract", "Contracts", "fixtures match the schemas"),
    ("fixture_still_matches", "Contracts", "regression guard on every fixture"),
    ("every_scenario_has_a_fixture", "Contracts", "scenarios and files agree"),
    ("every_review_reason", "Contracts", "all 4 escalation reasons exercised"),
    ("submission_sample", "Contracts", "one entry per fixture"),
    # Specific claims first: _area_for takes the first needle that matches, so the
    # per-file catch-alls below have to come last or they would swallow everything.
    ("token_a_blank_used", "Escalation wording", "the blank token is quoted, not summarised"),
    ("empty_value_is_called_blank", "Escalation wording", "nothing is never quoted as \"\""),
    ("side_that_was_blank", "Escalation wording", "the side that was blank is the side named"),
    ("long_value_does_not_run", "Escalation wording", "a pasted address is truncated"),
    ("quote_in_the_value", "Escalation wording", "quotes survive for the screen to escape"),
    ("wrong_document_is_named", "Escalation wording", "the file names what it declares itself"),
    ("unreadable_names_the_file", "Escalation wording", "the file that would not open is named"),
    ("test_evidence.py", "Escalation wording", "edges: none, both sides, no status"),
    ("english_word_is_not_a_shipment", "Shipment reference", "INTERNATIONAL is not a reference"),
    ("reference_is_read_from_the_subject", "Shipment reference", "both shapes, and neither"),
    ("subject_wins_over_the_body", "Shipment reference", "the row shows what the list shows"),
    ("first_reference_wins", "Shipment reference", "repeatable, never \"any of them\""),
    ("waiting_on_a_draft_bl_can_be_chased", "Shipment reference", "the chase list keeps its key"),
    ("test_shipment_ref.py", "Shipment reference", "case, absence, and the entry it writes"),
]
UNGROUPED = "Other"


def _area_for(nodeid: str) -> tuple[str, str]:
    for needle, area, claim in REPORT_AREAS:
        if needle in nodeid:
            return area, claim

    return UNGROUPED, ""


def pytest_terminal_summary(terminalreporter, exitstatus: int) -> None:
    """Print what was verified, not just how many assertions ran."""
    passed = terminalreporter.stats.get("passed", [])
    failed = terminalreporter.stats.get("failed", [])
    if not passed and not failed:
        return

    grouped: dict[str, dict[str, list[int]]] = {}
    for report in passed + failed:
        area, claim = _area_for(report.nodeid)
        bucket = grouped.setdefault(area, {}).setdefault(claim, [0, 0])
        bucket[0 if report.outcome == "passed" else 1] += 1

    order = [a for _, a, _ in REPORT_AREAS if a in grouped]
    seen: list[str] = []
    for area in order + sorted(grouped):
        if area not in seen and area in grouped:
            seen.append(area)

    write = terminalreporter.write_line
    write("")
    write("═" * 74)
    write("  VERIFICATION REPORT — shipping document verification")
    write("═" * 74)
    for area in seen:
        claims = grouped[area]
        total = sum(ok + bad for ok, bad in claims.values())
        write("")
        write(f"  {area.upper():<22}{total:>4} checks")
        for claim, (ok, bad) in claims.items():
            mark = "✓" if bad == 0 else "✗"
            write(f"    {mark} {claim or '(ungrouped)':<56}{ok:>3}")
    write("")
    write("─" * 74)
    total_ok, total_bad = len(passed), len(failed)
    verdict = "ALL VERIFIED" if total_bad == 0 else f"{total_bad} FAILING"
    write(f"  {verdict}   {total_ok} passed, {total_bad} failed")
    write("═" * 74)


@pytest.fixture(autouse=True)
def reports_start_with_nothing_held_back():
    """Reports remember what they filed recently, to hold back repeats. Each test
    starts with nothing remembered, so one test's rows never hold back another's."""
    from backend import reports

    reports.forget()
    yield
    reports.forget()


@pytest.fixture(autouse=True)
def fresh_rate_limit_window() -> None:
    """Every test starts with nobody counted by the rate limiter. The tests share one
    mailbox token, so without this /mailbox calls from earlier tests pile into one
    budget and a later test gets 429 depending on the order the suite runs in."""
    from backend import middleware

    middleware._seen.clear()
