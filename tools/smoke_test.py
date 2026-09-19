#!/usr/bin/env python3
"""Prove the loader reaches the data, both from disk and over HTTP.

    python3 tools/smoke_test.py ../
    python3 tools/smoke_test.py http://localhost:8081
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from loader import Inbox  # noqa: E402

EXPECTED_EMAILS = 520
EXPECTED_WITH_ATTACHMENTS = 126
SAMPLE_EMAIL_ID = "email_004"
DEFAULT_SOURCE = "../"


def count_problems(emails: int, with_attachments: int) -> list[str]:
    """A loader returning zero records is the documented failure mode of a
    misconfigured bind mount, so fail loudly rather than degrade quietly."""
    problems = []
    if emails != EXPECTED_EMAILS:
        problems.append(f"expected {EXPECTED_EMAILS} emails, got {emails}")
    if with_attachments != EXPECTED_WITH_ATTACHMENTS:
        problems.append(f"expected {EXPECTED_WITH_ATTACHMENTS} with attachments, "
                        f"got {with_attachments}")

    return problems


def report(source: str) -> list[str]:
    inbox = Inbox(source)
    emails = inbox.emails()
    with_attachments = [e for e in emails if e["attachments"]]
    sample = inbox.get(SAMPLE_EMAIL_ID)
    head = inbox.read_text(sample["attachments"][0]).splitlines()[0]

    print(f"source              {source}")
    print(f"emails              {len(emails)} (expected {EXPECTED_EMAILS})")
    print(f"with attachments    {len(with_attachments)} (expected {EXPECTED_WITH_ATTACHMENTS})")
    print(f"{SAMPLE_EMAIL_ID} SI head   {head}")

    return count_problems(len(emails), len(with_attachments))


def main() -> int:
    problems = report(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_SOURCE)
    if not problems:
        print("\nOK")
        return 0

    print("\nFAIL")
    for problem in problems:
        print(f"  - {problem}")

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
