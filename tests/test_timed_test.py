"""The timing packet, and the two ways it could quietly produce a wrong number.

The mentor asked for a timed manual-versus-system comparison as the impact
evidence. A badly built one is worse than none, because a judge will take it
apart, so the two things that would invalidate it are held here.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from cli.timed_test import FIELD_NAMES, SAMPLE, build, comparisons, pick, score

ROOT = Path(__file__).resolve().parents[1]


def test_the_reader_is_given_the_same_names_the_scorer_expects() -> None:
    """The sheet tells them to write "Gross weight". The results carry
    `gross_weight_kg`, which a naive underscore swap turns into "gross weight
    kg", so every correct answer would score as wrong, and the test would
    report a human accuracy far below the truth."""
    assert FIELD_NAMES["gross_weight_kg"] == "Gross weight"
    assert FIELD_NAMES["container_count"] == "Containers"
    for shown in FIELD_NAMES.values():
        assert "_" not in shown


def test_the_sample_is_stratified_and_not_all_mismatches() -> None:
    """Ten mismatches in a row teaches the reader to expect one; ten clean pairs
    teaches them to stop looking. Either way the timing is of a different task
    from the one the system does."""
    assert SAMPLE["OK"] > SAMPLE["MISMATCH"], "the corpus is 63 OK to 46 mismatch"
    assert SAMPLE["NEEDS_REVIEW"] >= 1


def test_the_packet_never_names_the_email(tmp_path: Path) -> None:
    """`docs.SI.name` is "email_520_SI.txt". Written out under that name, the
    reader can look the answer up in results.js and the timing measures typing
    speed."""
    build(tmp_path)

    for folder in sorted(p for p in tmp_path.iterdir() if p.is_dir()):
        assert sorted(f.name for f in folder.iterdir()) == [
            "draft-bill-of-lading.txt", "shipping-instruction.txt"]
        for document in folder.iterdir():
            assert "email_" not in document.read_text(encoding="utf-8")


def test_the_packet_is_the_same_every_time(tmp_path: Path) -> None:
    """Two people timing different pairs cannot be averaged together."""
    one, two = tmp_path / "a", tmp_path / "b"
    build(one)
    build(two)

    assert json.loads((one / "key.json").read_text()) == json.loads((two / "key.json").read_text())


def test_a_reader_who_gets_everything_right_scores_perfectly(tmp_path: Path, capsys) -> None:
    """The scorer has to agree with its own key, or the number is meaningless."""
    build(tmp_path)
    key = json.loads((tmp_path / "key.json").read_text())

    with (tmp_path / "answers.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["pair", "seconds", "verdict", "fields_that_differ", "who"])
        for pair, answer in sorted(key.items()):
            fields = "; ".join(FIELD_NAMES.get(f, f) for f in answer["defect_fields"])
            writer.writerow([pair, 120, answer["status"], fields, "tester"])

    score(tmp_path)
    printed = capsys.readouterr().out

    assert f"verdict correct       {len(key)} of {len(key)}" in printed
    assert f"and the exact fields  {len(key)} of {len(key)}" in printed
    assert "where it went wrong" not in printed


def test_a_missed_field_is_counted_even_when_the_verdict_was_right(tmp_path: Path, capsys) -> None:
    """Saying MISMATCH while naming only one of two differing fields is a miss.
    It is the commonest way a person goes wrong at speed, and the number that
    makes the comparison worth quoting."""
    build(tmp_path)
    key = json.loads((tmp_path / "key.json").read_text())
    two_fields = next((p, a) for p, a in sorted(key.items()) if len(a["defect_fields"]) >= 2)
    pair, answer = two_fields

    with (tmp_path / "answers.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["pair", "seconds", "verdict", "fields_that_differ", "who"])
        writer.writerow([pair, 90, answer["status"],
                         FIELD_NAMES.get(answer["defect_fields"][0]), "tester"])

    score(tmp_path)
    printed = capsys.readouterr().out

    assert "verdict correct       1 of 1" in printed
    assert "and the exact fields  0 of 1" in printed


def test_every_pair_carries_both_documents() -> None:
    pool = pick(comparisons())

    assert len(pool) == sum(SAMPLE.values())
    for email in pool:
        assert email["docs"]["SI"]["text"] and email["docs"]["BL"]["text"]
