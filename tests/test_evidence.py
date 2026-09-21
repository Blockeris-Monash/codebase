"""The evidence numbers are computed by small pure functions, so they are checked on tiny inputs."""
from __future__ import annotations

from cli import evidence as ev


def result(status=None, reason=None, defects=(), category="BL_COMPARISON", attachments=2):
    return {"id": "x", "category": category, "n_attachments": attachments, "status": status,
            "review_reason": reason, "defect_fields": list(defects)}


def test_pipeline_summary_counts_outcomes_reasons_and_defect_fields() -> None:
    results = [result("OK"), result("OK"), result("MISMATCH", defects=["shipper", "port_of_loading"]),
               result("MISMATCH", defects=["shipper"]), result("NEEDS_REVIEW", reason="missing_value"),
               result(None, category="SPAM", attachments=0)]

    summary = ev.pipeline_summary(results)

    assert summary["emails"] == 6 and summary["comparisons"] == 5
    assert summary["status"] == {"OK": 2, "MISMATCH": 2, "NEEDS_REVIEW": 1}
    assert summary["reasons"] == {"missing_value": 1}
    assert summary["defect_fields"] == {"shipper": 2, "port_of_loading": 1}
    assert summary["auto_cleared_share"] == 0.4


def test_classifier_summary_reports_agreement_with_the_keyword_fallback() -> None:
    classified = {"email_001": {"category": "SPAM", "confidence": 1.0},
                  "email_002": {"category": "GENERAL", "confidence": 0.5}}
    emails = {"email_001": {"subject": "bitcoin offer", "body": "exclusive offer", "attachments": []},
              "email_002": {"subject": "berthing", "body": "vessel", "attachments": ["a", "b"]}}

    summary = ev.classifier_summary(classified, emails)

    assert summary["total"] == 2 and summary["agree_with_fallback"] == 1
    assert summary["disagreements"] == [("email_002", "GENERAL", "BL_COMPARISON")]
    assert summary["low_confidence"] == 1


def test_hand_label_accuracy_lists_the_wrong_ones() -> None:
    classified = {"email_001": {"category": "SPAM"}, "email_002": {"category": "GENERAL"}}
    labels = {"_note": "ignored", "email_001": "SPAM", "email_002": "SI_REQUEST", "email_003": "SPAM"}

    accuracy = ev.hand_label_accuracy(classified, labels)

    assert accuracy == {"labelled": 2, "correct": 1, "ambiguous": 0, "wrong": [("email_002", "GENERAL", "SI_REQUEST")]}


def test_hand_label_accuracy_leaves_out_undecided_cases() -> None:
    classified = {"email_001": {"category": "SPAM"}, "email_002": {"category": "GENERAL"}}
    labels = {"email_001": "SPAM", "email_002": "AMBIGUOUS"}

    accuracy = ev.hand_label_accuracy(classified, labels)

    assert accuracy == {"labelled": 1, "correct": 1, "ambiguous": 1, "wrong": []}
