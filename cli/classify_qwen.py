#!/usr/bin/env python3
"""Classify every email on Qwen and save one ClassificationResult (contract 02) per email.

    QWEN_API_KEY=... QWEN_BASE_URL=... python3 -m cli.classify_qwen

Why this exists: backend/classify.py is a Gemini call with a small daily limit, so it cannot cover
520 emails. This batch tool does not replace or edit it. It uses the same five categories and
writes results/classifications/<email_id>.json, which cli.make_results picks up for the UI.

It also tells the model which files are attached, and that a request to *send* a draft BL with
nothing attached is an SI_REQUEST (the open BL_COMPARISON false positive in docs/04-classifier.md).
A rerun skips saved results.
"""
from __future__ import annotations

import argparse
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from backend.extract.qwen import DEFAULT_BASE_URL, DEFAULT_MODEL, USER_AGENT, Post, http_post, json_in

ROOT = Path(__file__).resolve().parents[1]
CATEGORIES = ("BL_COMPARISON", "SI_REQUEST", "INVOICE_QUERY", "GENERAL", "SPAM")
TIERS = {"1.0": 1.0, "0.85": 0.85, "0.65": 0.65, "0.50": 0.5}
TRIES = 4

PROMPT = """You are an AI shipping operations email triage classifier.
Classify this email into EXACTLY ONE category.

Categories:
- BL_COMPARISON: Asking to check, verify, confirm, or compare draft Bill of Lading (BL) against Shipping Instruction (SI).
- SI_REQUEST: Requesting to create or submit a new Shipping Instruction.
- INVOICE_QUERY: Inquiries about ocean invoices, D&D / detention fees, freight billing.
- GENERAL: Internal operational updates, vessel berthing notices, daily schedules.
- SPAM: Phishing, scams, promotions, or external spam.

A comparison needs both documents. If the email only asks someone to SEND the draft BL and nothing
is attached, it is an SI_REQUEST, not a BL_COMPARISON.

Confidence tiers (answer with the string):
- "1.0": explicit, unambiguous intent.
- "0.85": clear intent, informal phrasing.
- "0.65": several topics, one is primary.
- "0.50": vague or conflicting signals, best guess.

Reply with only one JSON object with these keys: category, confidence_tier, evidence
(evidence is a short verbatim excerpt from the email that justifies the category).

Email:
"""


def build_prompt(record: dict) -> str:
    files = ", ".join(Path(a).name for a in record["attachments"]) or "none"
    return (f"{PROMPT}- Email ID: {record['email_id']}\n- From: {record['from']}\n"
            f"- Subject: {record['subject']}\n- Attached files: {files}\n- Body:\n{record['body'][:1500]}\n")


def classify_with_qwen(record: dict, post: Post = http_post, key: str | None = None,
                       base_url: str | None = None) -> dict:
    key = key or os.environ.get("QWEN_API_KEY")
    if not key:
        raise RuntimeError("QWEN_API_KEY is not set")
    base_url = (base_url or os.environ.get("QWEN_BASE_URL", DEFAULT_BASE_URL)).rstrip("/")

    reply = post(
        f"{base_url}/v1/messages",
        {"content-type": "application/json", "anthropic-version": "2023-06-01",
         "x-api-key": key, "user-agent": USER_AGENT},
        {"model": os.environ.get("QWEN_MODEL", DEFAULT_MODEL), "max_tokens": 4096, "temperature": 0,
         "messages": [{"role": "user", "content": build_prompt(record)}]})

    text = "".join(block.get("text", "") for block in reply["content"])
    try:
        parsed = json.loads(json_in(text))
        category, tier, evidence = parsed["category"], str(parsed["confidence_tier"]), str(parsed["evidence"])
    except (ValueError, KeyError, TypeError) as error:
        raise ValueError(f"Qwen reply is not a classification: {text[:200]!r}") from error
    if category not in CATEGORIES or tier not in TIERS:
        raise ValueError(f"Qwen reply has an unknown category or confidence: {category!r}, {tier!r}")

    return {"email_id": record["email_id"], "category": category, "decided_by": "llm",
            "confidence": TIERS[tier], "evidence": evidence}


def classify_with_retries(record: dict, **kwargs) -> dict:
    for attempt in range(1, TRIES + 1):
        try:
            return classify_with_qwen(record, **kwargs)
        except Exception:  # rate limit, timeout or a malformed reply: wait, then ask again
            if attempt == TRIES:
                raise
            time.sleep(2 * attempt)


def run_batch(data_dir: Path, out_dir: Path, workers: int = 2, limit: int | None = None,
              **kwargs) -> tuple[int, int]:
    out_dir.mkdir(parents=True, exist_ok=True)
    todo = [f for f in sorted((data_dir / "inbox").glob("email_*.json")) if not (out_dir / f"{f.stem}.json").exists()]
    todo = todo[:limit] if limit else todo

    def one(inbox_file: Path) -> str:
        result = classify_with_retries(json.loads(inbox_file.read_text(encoding="utf-8")), **kwargs)
        (out_dir / f"{inbox_file.stem}.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        return result["category"]

    done = failed = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(one, f): f for f in todo}
        for i, future in enumerate(as_completed(futures), 1):
            try:
                future.result()
                done += 1
            except Exception as error:
                failed += 1
                print(f"FAILED {futures[future].stem}: {error}", flush=True)
            if i % 20 == 0 or i == len(todo):
                print(f"{i}/{len(todo)} done ({failed} failed)", flush=True)
    return done, failed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--data", default=str(ROOT / "data"))
    parser.add_argument("--out", default=str(ROOT / "results" / "classifications"))
    parser.add_argument("--workers", type=int, default=2, help="4 gets 429s from the gateway")
    parser.add_argument("--limit", type=int, default=None, help="only the first N unsaved emails")
    args = parser.parse_args()
    done, failed = run_batch(Path(args.data), Path(args.out), workers=args.workers, limit=args.limit)
    print(f"saved {done}, failed {failed}, output {args.out}")


if __name__ == "__main__":
    main()
