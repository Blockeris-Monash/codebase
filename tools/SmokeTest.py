#!/usr/bin/env python3
"""Prove the loader reaches the data, both from disk and over HTTP.

    python3 tools/SmokeTest.py ../
    python3 tools/SmokeTest.py http://localhost:8081
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from Loader import Inbox  # noqa: E402

EXPECTED_EMAILS = 520
EXPECTED_WITH_ATTACHMENTS = 126


def main():
    source = sys.argv[1] if len(sys.argv) > 1 else "../"
    inbox = Inbox(source)
    emails = inbox.emails()
    with_attachments = [e for e in emails if e["attachments"]]

    print(f"source              {source}")
    print(f"emails              {len(emails)} (expected {EXPECTED_EMAILS})")
    print(f"with attachments    {len(with_attachments)} (expected {EXPECTED_WITH_ATTACHMENTS})")

    sample = inbox.get("email_004")
    si = inbox.read_text(sample["attachments"][0])
    print(f"email_004 SI head   {si.splitlines()[0]}")

    problems = []
    if len(emails) != EXPECTED_EMAILS:
        problems.append(f"expected {EXPECTED_EMAILS} emails, got {len(emails)}")
    if len(with_attachments) != EXPECTED_WITH_ATTACHMENTS:
        problems.append(f"expected {EXPECTED_WITH_ATTACHMENTS} with attachments, "
                        f"got {len(with_attachments)}")
    if problems:
        print("\nFAIL")
        for p in problems:
            print(f"  - {p}")
        return 1
    print("\nOK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
