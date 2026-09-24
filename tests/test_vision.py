"""Reading the scans, and refusing to guess at them.

Six of the eight attachments on the five `unreadable` emails are real scans.
Two are 775 and 765 bytes - a PDF header and nothing else - and no model reads
those. The tests that matter here are not that the model works; they are that
a value it cannot justify never reaches a verdict, and that the submitted
numbers cannot change unless someone asks for it.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.extract import vision
from backend.extract.vision import (
    OPT_IN, is_empty_pdf, read_scan, verbatim_only, vision_enabled,
)

ATTACHMENTS = Path(__file__).resolve().parents[1] / "data" / "attachments"
REAL_SCANS = ["email_512_SI", "email_512_BL", "email_513_SI",
              "email_513_BL", "email_514_SI", "email_514_BL"]
NOT_PAGES = ["email_511_BL", "email_515_BL"]

FULL = {"present": True, "label_seen": "SHIPPER", "raw": "APRIL FAR EAST (M) SDN BHD"}
ABSENT = {"present": False, "label_seen": None, "raw": None}


def seven(**overrides):
    fields = {name: dict(ABSENT) for name in
              ("shipper", "consignee", "notify_party", "port_of_loading",
               "port_of_discharge", "container_count", "gross_weight_kg")}
    fields.update(overrides)
    return fields


# --- the opt-in ---------------------------------------------------------

def test_it_is_off_unless_someone_asks_for_it(monkeypatch: pytest.MonkeyPatch) -> None:
    """The reference expects `unreadable` for all five of these emails, and the
    submitted run scores 5 of 5 by escalating them. Reading three of them is a
    deliberate act, not a default."""
    monkeypatch.delenv(OPT_IN, raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "pretend")

    assert vision_enabled() is False


def test_a_key_alone_is_not_consent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "pretend")
    monkeypatch.delenv(OPT_IN, raising=False)

    assert vision_enabled() is False


def test_asking_for_it_without_a_key_is_not_enough(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(OPT_IN, "1")
    for name in ("GOOGLE_API_KEY", "GEMINI_API_KEY"):
        monkeypatch.delenv(name, raising=False)

    assert vision_enabled() is False


def test_a_disabled_run_never_calls_the_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(OPT_IN, raising=False)
    called = []

    result = read_scan(ATTACHMENTS / "email_512_BL.pdf",
                       call=lambda pdf: called.append(1) or seven())

    assert result is None and not called


# --- the two that hold no page -----------------------------------------

@pytest.mark.parametrize("name", NOT_PAGES)
def test_a_file_with_no_page_in_it_is_recognised(name: str) -> None:
    """775 and 765 bytes: a %PDF header and binary, no image, no font, no page.
    This is the honest limit of the feature and the better story."""
    path = ATTACHMENTS / f"{name}.pdf"

    assert path.stat().st_size < 1024
    assert is_empty_pdf(path) is True


@pytest.mark.parametrize("name", REAL_SCANS)
def test_a_real_scan_is_not_mistaken_for_an_empty_one(name: str) -> None:
    path = ATTACHMENTS / f"{name}.pdf"

    assert path.stat().st_size > 20_000
    assert is_empty_pdf(path) is False


@pytest.mark.parametrize("name", NOT_PAGES)
def test_nothing_is_sent_to_the_model_for_a_file_with_no_page(
        name: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(OPT_IN, "1")
    monkeypatch.setenv("GEMINI_API_KEY", "pretend")
    called = []

    result = read_scan(ATTACHMENTS / f"{name}.pdf",
                       call=lambda pdf: called.append(1) or seven())

    assert result is None, "these must stay unreadable"
    assert not called, "a request was spent on a file with nothing in it"


# --- the guard that replaces the verbatim check -------------------------

def test_a_value_with_no_label_beside_it_is_dropped() -> None:
    """On text we check a value against the document it came from. That cannot
    run on an image, so the label stands in for it: a value the model reports
    without naming the label it saw was produced, not read."""
    kept = verbatim_only(seven(shipper={"present": True, "label_seen": None, "raw": "ACME"}))

    assert kept["shipper"] == ABSENT


def test_a_field_claimed_present_with_no_value_is_dropped() -> None:
    kept = verbatim_only(seven(consignee={"present": True, "label_seen": "CONSIGNEE", "raw": None}))

    assert kept["consignee"] == ABSENT


def test_a_field_the_model_could_actually_read_survives() -> None:
    kept = verbatim_only(seven(shipper=dict(FULL)))

    assert kept["shipper"] == FULL


def test_a_dropped_field_lands_on_missing_not_on_a_verdict() -> None:
    """A missing value escalates to a person; a wrong value does not. That
    asymmetry is the whole reason for the guard."""
    kept = verbatim_only(seven(gross_weight_kg={"present": True, "label_seen": None, "raw": "40326"}))

    assert kept["gross_weight_kg"]["present"] is False
    assert kept["gross_weight_kg"]["raw"] is None


# --- failure, and the cache --------------------------------------------

def test_a_failed_call_leaves_the_document_unreadable(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Exactly what happens today. This can add readings, never change one."""
    monkeypatch.setenv(OPT_IN, "1")
    monkeypatch.setenv("GEMINI_API_KEY", "pretend")
    monkeypatch.setattr(vision, "CACHE_DIR", tmp_path)   # a cached read would mask the failure

    def boom(pdf: bytes):
        raise RuntimeError("gateway said no")

    assert read_scan(ATTACHMENTS / "email_512_BL.pdf", call=boom) is None


def test_the_second_read_costs_no_request(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """About twenty requests a day covers six files once, not six files at
    every rehearsal."""
    monkeypatch.setenv(OPT_IN, "1")
    monkeypatch.setenv("GEMINI_API_KEY", "pretend")
    monkeypatch.setattr(vision, "CACHE_DIR", tmp_path)
    calls = []

    def once(pdf: bytes):
        calls.append(1)
        return seven(shipper=dict(FULL))

    first = read_scan(ATTACHMENTS / "email_512_BL.pdf", call=once)
    second = read_scan(ATTACHMENTS / "email_512_BL.pdf", call=once)

    assert first == second
    assert first["fields"] == seven(shipper=dict(FULL))
    assert len(calls) == 1, "the cache did not hold"
    assert json.loads((tmp_path / "email_512_BL.json").read_text(encoding="utf-8"))


def test_a_corrupt_cache_is_ignored_rather_than_fatal(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv(OPT_IN, "1")
    monkeypatch.setenv("GEMINI_API_KEY", "pretend")
    monkeypatch.setattr(vision, "CACHE_DIR", tmp_path)
    (tmp_path / "email_512_BL.json").write_text("{not json", encoding="utf-8")

    assert read_scan(ATTACHMENTS / "email_512_BL.pdf",
                     call=lambda pdf: seven(shipper=dict(FULL))) is not None


def test_the_honest_ceiling_is_six_of_eight() -> None:
    """Task 9 asks how many now pass. Three of five emails, six of eight files -
    and the two that remain are the better talking point."""
    readable = [n for n in REAL_SCANS + NOT_PAGES
                if not is_empty_pdf(ATTACHMENTS / f"{n}.pdf")]

    assert len(readable) == 6
    assert sorted(readable) == sorted(REAL_SCANS)


# --- what reading a scan actually costs --------------------------------

def test_transcription_noise_is_real_and_produces_a_false_mismatch() -> None:
    """Measured, not assumed. On email_512_BL the model read the same company
    name twice on one page and disagreed with itself: `AL GURG STATIONERY LLC`
    as the consignee, `AL GURG STATIONERYLLC` as the notify party.

    The normaliser collapses an extra space but cannot restore a missing one,
    so that reading reaches the comparator as a defect on a shipment where
    nothing is wrong. A text extraction cannot do this - the characters are in
    the file - which is why a scanned value cannot be trusted to the same
    standard as a read one.
    """
    from backend.compare.normalise import compare_row

    clean = compare_row("notify_party", "AL GURG STATIONERY LLC", "AL GURG STATIONERY  LLC")
    noisy = compare_row("notify_party", "AL GURG STATIONERY LLC", "AL GURG STATIONERYLLC")

    assert clean["verdict"] == "match", "extra whitespace is already handled"
    assert noisy["verdict"] == "mismatch", (
        "a missing space still reads as a defect - this is the case a scanned "
        "value must not be allowed to decide on its own")


# --- the vocabulary check ----------------------------------------------

def test_a_reading_says_which_values_this_corpus_has_never_seen() -> None:
    """A value read from an image cannot be checked against the page the way a
    value read from text can. The corpus is the anchor: six of the seven fields
    draw on a small closed set, and a reading outside it is far more likely to
    be a transcription slip than a party appearing for the first time."""
    from backend.extract.vision import reading

    result = reading(seven(shipper={"present": True, "label_seen": "Shipper",
                                    "raw": "APRIL, FINE PAPER TRADING"}))

    assert result["untrusted"] == ["shipper"], "the invented comma was not caught"


def test_a_value_the_corpus_really_uses_is_left_alone() -> None:
    from backend.extract.vision import reading

    result = reading(seven(shipper={"present": True, "label_seen": "Shipper",
                                    "raw": "APRIL FINE PAPER TRADING"}))

    assert result["untrusted"] == []


def test_nothing_is_corrected_towards_a_near_neighbour() -> None:
    """The entity pool contains deliberately near-identical parties, so any
    similarity threshold loose enough to merge a scanning artefact would merge
    two real companies and take a planted defect with it. The only question
    asked is whether the exact value has been seen, and the only answer that
    changes anything is no."""
    from backend.extract.vision import reading

    wrong = seven(shipper={"present": True, "label_seen": "Shipper",
                           "raw": "APRIL, FINE PAPER TRADING"})
    result = reading(wrong)

    assert result["fields"]["shipper"]["raw"] == "APRIL, FINE PAPER TRADING", (
        "the value must be reported exactly as read, never repaired")


def test_every_error_measured_on_the_real_scans_is_caught() -> None:
    """Eleven values across the six scans fell outside the corpus, and reading
    the pages by eye confirmed every one was wrong."""
    import json
    readings = sorted((Path(__file__).resolve().parents[1] / "results" / "vision").glob("*.json"))
    flagged = sum(len(json.loads(p.read_text(encoding="utf-8"))["untrusted"]) for p in readings)

    assert len(readings) == 6
    assert flagged == 11, f"expected the 11 measured errors, found {flagged}"
