"""The comparison stage catches every planted defect and raises no false alarm on harmless edits.

Uses the saved extracts, so it skips when they are absent."""
from __future__ import annotations

import pytest

from cli import mutation_check as mc

pytestmark = pytest.mark.skipif(not mc.EXTRACTS.exists(), reason="saved extracts not present")


@pytest.fixture(scope="module")
def report() -> dict:
    return mc.run_check()


def test_there_are_matching_emails_to_mutate(report: dict) -> None:
    assert report["emails"] >= 50


def test_every_defect_is_caught_on_exactly_the_changed_field(report: dict) -> None:
    missed = {key: s["missed"] for key, s in report["defects"].items() if s["missed"]}
    assert not missed, missed


def test_harmless_edits_stay_ok(report: dict) -> None:
    false_alarms = {key: s["false_alarms"] for key, s in report["harmless"].items() if s["false_alarms"]}
    assert not false_alarms, false_alarms
