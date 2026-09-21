#!/usr/bin/env python3
"""Classify every email with Qwen and save one ClassificationResult JSON each.

    python3 -m cli.classify_qwen --data data --out results/classifications

The UI builder (cli.make_results) reads these files, so the category shown for an email is the
model's, not the keyword fallback. A rerun skips saved results and retries the ones that failed.

Same prompt and schema as backend.classify (Gemini, 20 requests a day on the free key), sent to
the Qwen gateway instead. Once backend.classify itself moves to Qwen (issue #16) this script can
call it and shrink to the loop.
"""
from __future__ import annotations

import argparse
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from pydantic import ValidationError

from backend.classify import ClassificationFailed, GeminiClassificationSchema
from backend.extract.qwen import DEFAULT_BASE_URL, DEFAULT_MODEL, USER_AGENT, Post, http_post, json_in

ROOT = Path(__file__).resolve().parents[1]

PROMPT = """You are an AI shipping operations email triage classifier.
Classify this email into EXACTLY ONE category.

Categories:
- BL_COMPARISON: Asking to check, verify, confirm, or compare draft Bill of Lading (BL) against Shipping Instruction (SI).
- SI_REQUEST: Requesting to create or submit a new Shipping Instruction.
- INVOICE_QUERY: Inquiries about ocean invoices, D&D / detention fees, freight billing.
- GENERAL: Internal operational updates, vessel berthing notices, daily schedules.
- SPAM: Phishing, scams, promotions, or external spam.

Confidence tiers: "1.0" explicit and unambiguous, "0.85" clear but informal, "0.65" several signals and one is primary, "0.50" vague or conflicting (best guess).

Email Content:
- Email ID: {email_id}
- From: {sender}
- Subject: {subject}
- Body:
{body}

Reply with only one JSON object with these keys: "category", "confidence_tier", "evidence" (a short verbatim excerpt from the email)."""


def classify_email_qwen(email: dict, post: Post = http_post) -> dict:
    """The ClassificationResult (as a dict) for one inbox record, or ClassificationFailed."""
    key = os.environ.get("QWEN_API_KEY")
    if not key:
        raise ClassificationFailed("QWEN_API_KEY is not set")

    base_url = os.environ.get("QWEN_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
    prompt = PROMPT.format(email_id=email["email_id"], sender=email["from"], subject=email["subject"],
                           body=email["body"][:1500])
    try:
        reply = post(
            f"{base_url}/v1/messages",
            {"content-type": "application/json", "anthropic-version": "2023-06-01",
             "x-api-key": key, "user-agent": USER_AGENT},
            {"model": os.environ.get("QWEN_MODEL", DEFAULT_MODEL), "max_tokens": 4096, "temperature": 0,
             "messages": [{"role": "user", "content": prompt}]})
        reply_text = "".join(block.get("text", "") for block in reply["content"])
        parsed = GeminiClassificationSchema.model_validate_json(json_in(reply_text))
    except (ValidationError, KeyError, ValueError, OSError) as error:
        raise ClassificationFailed(f"{email['email_id']}: {error}") from error

    return {"email_id": email["email_id"], "category": parsed.category, "decided_by": "llm",
            "confidence": float(parsed.confidence_tier), "evidence": parsed.evidence}


def classify_with_retries(email: dict, post: Post, retries: int) -> dict | None:
    for attempt in range(retries):
        try:
            return classify_email_qwen(email, post)
        except ClassificationFailed:
            time.sleep(min(2 ** attempt, 8) if retries > 1 else 0)
    return None


def run_batch(inbox_dir: Path, out_dir: Path, post: Post = http_post, log=print,
              workers: int = 1, retries: int = 3) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    summary: dict = {"done": 0, "skipped": 0, "failed": []}
    files = sorted(inbox_dir.glob("email_*.json"))
    todo = [f for f in files if not (out_dir / f.name).exists()]
    summary["skipped"] = len(files) - len(todo)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        jobs = {pool.submit(classify_with_retries, json.loads(f.read_text(encoding="utf-8")), post, retries): f
                for f in todo}
        for number, job in enumerate(as_completed(jobs), 1):
            file = jobs[job]
            result = job.result()
            if result is None:
                summary["failed"].append(file.stem)
                log(f"[{number}/{len(todo)}] {file.stem}: FAILED")
                continue
            (out_dir / file.name).write_text(json.dumps(result, indent=2), encoding="utf-8")
            summary["done"] += 1
            log(f"[{number}/{len(todo)}] {file.stem}: {result['category']} ({result['confidence']})")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--data", default=str(ROOT / "data"))
    parser.add_argument("--out", default=str(ROOT / "results" / "classifications"))
    parser.add_argument("--workers", type=int, default=2)
    args = parser.parse_args()

    summary = run_batch(Path(args.data) / "inbox", Path(args.out), workers=args.workers)
    print(f"done {summary['done']}, skipped {summary['skipped']}, failed {len(summary['failed'])}")
    if summary["failed"]:
        print("failed:", " ".join(summary["failed"]))


if __name__ == "__main__":
    main()
