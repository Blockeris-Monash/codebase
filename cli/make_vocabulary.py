#!/usr/bin/env python3
"""Write down the values these documents actually use.

A value read from a scanned page cannot be checked against the page the way a
value read from text can - the characters are not there to compare against. The
corpus is the next best anchor: across the 192 text attachments, six of the
seven fields take a small closed set of values, and a scanned reading that is
not in that set is far more likely to be a transcription slip than a new party
appearing for the first time on an image-only page.

Written to a file rather than computed on demand so it can be read, reviewed and
diffed - the check is only as defensible as the list it checks against.
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

from backend.compare.normalise import normalise
from backend.contracts import FIELD_NAMES
from backend.read.documents import read_document
from backend.read.labels import canonical_field

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results" / "vocabulary.json"
TEXT_GLOB = "*.txt"
# Above this a field is taking free values rather than drawing from a set, and
# "not in the list" stops meaning anything. Weight is the one that crosses it.
CLOSED_SET_LIMIT = 60


def values_in(path: Path) -> list[tuple[str, str]]:
    """Every (field, normalised value) a text attachment yields."""
    _, pairs = read_document(path)
    found = []
    for label, value in pairs:
        field = canonical_field(label)
        if not field or not value:
            continue
        normalised = normalise(field, value)
        if normalised:
            found.append((field, normalised))

    return found


def collect(attachments: Path) -> dict[str, set[str]]:
    seen: dict[str, set[str]] = defaultdict(set)
    for path in sorted(attachments.glob(TEXT_GLOB)):
        for field, value in values_in(path):
            seen[field].add(value)

    return seen


def closed_only(seen: dict[str, set[str]]) -> dict[str, list[str]]:
    """Drop the fields that take free values - listing them proves nothing."""
    return {field: sorted(values) for field, values in seen.items()
            if field in FIELD_NAMES and len(values) <= CLOSED_SET_LIMIT}


def main() -> int:
    attachments = ROOT / "data" / "attachments"
    if not attachments.is_dir():
        print(f"no attachments at {attachments}", file=sys.stderr)
        return 1

    seen = collect(attachments)
    closed = closed_only(seen)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(closed, indent=2, ensure_ascii=False) + "\n",
                   encoding="utf-8", newline="\n")

    for field in FIELD_NAMES:
        count = len(seen.get(field, ()))
        kept = "closed" if field in closed else f"open, {count} values - not checkable"
        print(f"  {field:<18} {count:>4}  {kept}")
    print(f"\n  written to {OUT.relative_to(ROOT)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
