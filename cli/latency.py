#!/usr/bin/env python3
"""Time the real pipeline: how long one SI vs BL check takes with live Qwen, and whether the
live answer matches the saved one.

    python3 -m cli.latency --n 10        # needs QWEN_API_KEY; writes results/latency.json

Runs POST /extract-clean-compare?live=true (backend.app.run_pipeline) one email at a time, so the
numbers are per email, not per batch. python3 -m cli.evidence reads results/latency.json.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import random
import time
from pathlib import Path
from typing import Awaitable, Callable

from cli.evidence import latency_summary, load_results_js

ROOT = Path(__file__).resolve().parents[1]
SEED = 22


def pick(results: list[dict], n: int) -> list[dict]:
    """A repeatable spread of matching and mismatching emails that have both documents."""
    usable = [e for e in results if e.get("status") in ("OK", "MISMATCH") and e.get("docs", {}).get("SI") and e["docs"].get("BL")]
    random.Random(SEED).shuffle(usable)
    half = n // 2
    chosen = [e for e in usable if e["status"] == "OK"][:half] + [e for e in usable if e["status"] == "MISMATCH"][: n - half]
    return sorted(chosen, key=lambda e: e["id"])


def payload_for(entry: dict):
    from backend.app import PairedInput

    si, bl = entry["docs"]["SI"], entry["docs"]["BL"]
    return PairedInput(email_id=entry["id"], si_pairs=[tuple(p) for p in si["pairs"]],
                       bl_pairs=[tuple(p) for p in bl["pairs"]], si_title=si["title"], bl_title=bl["title"],
                       si_parse_status=si["parse_status"], bl_parse_status=bl["parse_status"])


async def measure(entries: list[dict], pipeline: Callable[..., Awaitable]) -> list[dict]:
    runs = []
    for entry in entries:
        started = time.perf_counter()
        result = await pipeline(payload_for(entry), live=True)
        seconds = time.perf_counter() - started
        same = result.status == entry["status"] and list(result.defect_fields) == list(entry["defect_fields"])
        runs.append({"email_id": entry["id"], "seconds": round(seconds, 1), "saved": entry["status"],
                     "live": result.status, "same": same})
    return runs


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--n", type=int, default=10)
    parser.add_argument("--results", default=str(ROOT / "frontend" / "results.js"))
    parser.add_argument("--out", default=str(ROOT / "results" / "latency.json"))
    args = parser.parse_args()

    from backend.app import run_pipeline

    entries = pick(load_results_js(Path(args.results)), args.n)
    runs = asyncio.run(measure(entries, run_pipeline))
    for run in runs:
        print(f"{run['email_id']}: {run['seconds']}s  saved {run['saved']}  live {run['live']}  {'same' if run['same'] else 'DIFFERENT'}")
    summary = {**latency_summary(runs), "runs": runs}
    Path(args.out).write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print({k: v for k, v in summary.items() if k != "runs"})


if __name__ == "__main__":
    main()
