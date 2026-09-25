"""Write submission.json: one entry per email, keyed by email_id, all 520 (contract 5).

Built from frontend/results.js, the saved results the page shows, so the file and the page
always agree. SI vs BL emails carry their check's status; every other kind is OK, as in
data/sample_submission.json.

    python -m cli.make_submission --out submission.json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def entry(email: dict) -> dict:
    if email["category"] != "BL_COMPARISON":
        return {"category": email["category"], "status": "OK", "review_reason": None,
                "has_defect": False, "defect_fields": []}
    return {"category": "BL_COMPARISON", "status": email["status"], "review_reason": email["review_reason"],
            "has_defect": email["status"] == "MISMATCH", "defect_fields": list(email["defect_fields"])}


def build(results: list[dict]) -> dict[str, dict]:
    return {e["id"]: entry(e) for e in sorted(results, key=lambda e: e["id"])}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--results", default=str(ROOT / "frontend" / "results.js"))
    parser.add_argument("--out", default=str(ROOT / "submission.json"))
    args = parser.parse_args(argv)

    src = Path(args.results).read_text(encoding="utf-8")
    submission = build(json.loads(src[src.index("["): src.rindex("]") + 1]))
    Path(args.out).write_text(json.dumps(submission, indent=2) + "\n", encoding="utf-8")
    print(f"{len(submission)} entries -> {args.out}")


if __name__ == "__main__":
    main()
