#!/usr/bin/env python3
"""Prove the rules-first path is both faster and unchanged, on demand.

    python3 -m cli.rules_first_check              # verdicts only, no model, no key
    python3 -m cli.rules_first_check --timed      # also A/B one email against the model

Two questions, deliberately separate, because they have different costs and
different audiences.

**Is it still right?** Runs both extractors through the same comparator over
every comparison email in the corpus and reports where the verdict differs.
Offline, no key, about a quarter of a second. This is the one that matters: a
faster answer that disagrees is not an improvement, it is a regression with a
stopwatch attached.

**Is it actually faster?** With `--timed`, runs one real email twice - once with
`SHIP_HAPPENS_RULES_FIRST=0` so the model is called, once with it on - against an
empty cache directory so neither run can be answered from disk. Needs a key and
spends two model calls, so it is opt-in.
"""
from __future__ import annotations

import argparse
import json
import os
import tempfile
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from backend import app
from backend.compare.comparator import compare
from backend.extract.rules import attachment_meta, document_extract

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA = ROOT / "data"
EXTRACTS = ROOT / "results" / "extracts"
TIMED_EMAIL = "email_004"          # a real mismatch, so the verdict is not trivially OK
OFF, ON = "0", "1"


def verdict_of(result) -> tuple:
    return result.status, result.review_reason, tuple(sorted(result.defect_fields))


def compare_both_paths(data_dir: Path) -> tuple[int, list[str]]:
    """Every comparison email, both extractors, one comparator."""
    disagreements: list[str] = []
    checked = 0

    for record in sorted((data_dir / "inbox").glob("email_*.json")):
        email = json.loads(record.read_text(encoding="utf-8"))
        attachments = email.get("attachments") or []
        if len(attachments) < 2:
            continue

        metas = {}
        for attachment in attachments:
            meta = attachment_meta(str(attachment))
            metas[meta["declared_role"]] = meta
        if set(metas) != {"SI", "BL"}:
            continue

        model = {}
        for role, meta in metas.items():
            saved = EXTRACTS / f"{Path(meta['path']).stem}.json"
            if saved.exists():
                model[role] = json.loads(saved.read_text(encoding="utf-8"))
        if len(model) != 2:
            continue

        by_rule = {role: document_extract(str(data_dir), email["email_id"], meta)
                   for role, meta in metas.items()}

        theirs = verdict_of(compare(email["email_id"], model["SI"], model["BL"]))
        ours = verdict_of(compare(email["email_id"], by_rule["SI"], by_rule["BL"]))
        checked += 1
        if theirs != ours:
            disagreements.append(f"{email['email_id']}: model={theirs} rules={ours}")

    return checked, disagreements


def time_one_email(data_dir: Path) -> None:
    """The same email twice, with the cache pointed at an empty folder so the
    model path is genuinely exercised rather than answered from disk."""
    record = data_dir / "inbox" / f"{TIMED_EMAIL}.json"
    if not record.exists():
        print(f"  {TIMED_EMAIL} not in {data_dir}, skipping the timed run")
        return

    from fastapi.testclient import TestClient

    email = json.loads(record.read_text(encoding="utf-8"))
    payload = {"email_id": TIMED_EMAIL, "from_email": email["from"],
               "subject": email["subject"], "body": email["body"],
               "attachments": email["attachments"]}

    client = TestClient(app.app)
    empty, real = Path(tempfile.mkdtemp()), app.EXTRACTS_DIR
    was = os.environ.get(app.RULES_FIRST)
    try:
        for flag, label in ((OFF, "model  "), (ON, "rules  ")):
            app.EXTRACTS_DIR = empty
            os.environ[app.RULES_FIRST] = flag
            started = time.monotonic()
            response = client.post("/process-email", json=payload)
            elapsed = time.monotonic() - started
            entry = (response.json().get("SubmissionEntry") or {}) if response.status_code == 200 else {}
            print(f"  {label} {elapsed:7.2f}s   status={entry.get('status')} "
                  f"defects={entry.get('defect_fields')}")
    finally:
        app.EXTRACTS_DIR = real
        if was is None:
            os.environ.pop(app.RULES_FIRST, None)
        else:
            os.environ[app.RULES_FIRST] = was


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--data", default=str(DEFAULT_DATA))
    parser.add_argument("--timed", action="store_true",
                        help="also A/B one email against the model (needs a key, spends 2 calls)")
    args = parser.parse_args()

    data_dir = Path(args.data)
    if not (data_dir / "inbox").is_dir():
        print(f"dataset not found at {data_dir} - pass --data")
        return 2

    started = time.monotonic()
    checked, disagreements = compare_both_paths(data_dir)
    elapsed = time.monotonic() - started

    print(f"  comparison emails   {checked}")
    print(f"  same verdict        {checked - len(disagreements)}")
    print(f"  different verdict   {len(disagreements)}")
    print(f"  rules path          {elapsed:.2f}s total, {elapsed * 1000 / max(checked, 1):.1f} ms per email")
    for line in disagreements:
        print(f"    {line}")

    if args.timed:
        print("\n  one email, cache bypassed, model against rules:")
        time_one_email(data_dir)

    return 1 if disagreements else 0


if __name__ == "__main__":
    raise SystemExit(main())
