#!/usr/bin/env python3
"""Build and score a manual-versus-system timing test.

    python3 -m cli.timed_test build --out timed-test      # make the packet
    python3 -m cli.timed_test score timed-test            # score the filled sheet

The mentor's answer to "what impact evidence would convince you" was: time a
person checking by hand and the system doing it, a few runs each, and compare the
averages. This builds the packet for the person half and scores it.

**The comparison has to be honest or a judge will take it apart.** Two rules are
built in:

Compare like with like. The number to quote for the system is the *live* path,
not a saved result - a person reading two documents against a database lookup is
not a measurement. `python3 -m cli.rules_first_check --timed` gives the live one.

Record accuracy, not just seconds. A person going quickly misses the subtle
cases: `AL GURG STATIONERY LLC` against `L.L.C.`, or a port where the bracketed
code matches on both documents and only the city differs. "Three minutes and
missed two of ten" is a stronger sentence than any time on its own, and it is the
half that connects to the 630-of-630 figure we already have.

The sample is stratified - five OK, four mismatch, one needing review - because
ten mismatches in a row teaches the reader to expect them, and ten clean ones
teaches them to stop looking. That ratio follows the corpus: 63 OK, 46 mismatch,
5 review.

Give it to someone who has not been staring at this dataset all week. Everyone on
the team is now a bad subject.
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import re
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "frontend" / "results.js"

# Following the corpus mix (63 OK / 46 mismatch / 5 review), not a round number.
SAMPLE = {"OK": 5, "MISMATCH": 4, "NEEDS_REVIEW": 1}
SEED = 20260926          # the finals date: same packet every time, for comparing runs
SHEET = "answers.csv"
KEY = "key.json"
# The names the reader is given, and the ids the results carry. Written out
# rather than derived: "gross_weight_kg" becomes "gross weight kg" under a naive
# underscore swap, which is not what anyone would write on the sheet, so the
# scorer would count every correct answer as wrong.
FIELD_NAMES = {
    "shipper": "Shipper",
    "consignee": "Consignee",
    "notify_party": "Notify party",
    "port_of_loading": "Port of loading",
    "port_of_discharge": "Port of discharge",
    "container_count": "Containers",
    "gross_weight_kg": "Gross weight",
}
FIELDS = list(FIELD_NAMES.values())


def comparisons() -> list[dict]:
    """Every email with a comparison, read from what the review app itself ships."""
    source = RESULTS.read_text(encoding="utf-8")
    match = re.search(r"=\s*(\[.*\])\s*;?\s*$", source, re.S)
    if not match:
        raise SystemExit(f"could not read {RESULTS}")

    everything = json.loads(match.group(1))

    def has_text(email: dict, role: str) -> bool:
        side = (email.get("docs") or {}).get(role) or {}
        return bool(side.get("text"))

    return [e for e in everything
            if e.get("rows") and has_text(e, "SI") and has_text(e, "BL")]


def pick(pool: list[dict]) -> list[dict]:
    rng = random.Random(SEED)
    chosen: list[dict] = []
    for status, how_many in SAMPLE.items():
        of_this_kind = [e for e in pool if e["status"] == status]
        chosen.extend(rng.sample(of_this_kind, min(how_many, len(of_this_kind))))
    rng.shuffle(chosen)                      # so the order gives nothing away

    return chosen


def build(out: Path) -> int:
    chosen = pick(comparisons())
    if not chosen:
        raise SystemExit("no comparison emails found")

    out.mkdir(parents=True, exist_ok=True)
    key = {}
    for number, email in enumerate(chosen, 1):
        folder = out / f"{number:02d}"
        folder.mkdir(exist_ok=True)
        # Role-only filenames. docs.SI.name is "email_520_SI.txt", which would
        # hand the reader the email id and let them look the answer up.
        (folder / "shipping-instruction.txt").write_text(
            email["docs"]["SI"]["text"], encoding="utf-8")
        (folder / "draft-bill-of-lading.txt").write_text(
            email["docs"]["BL"]["text"], encoding="utf-8")
        key[f"{number:02d}"] = {
            "email_id": email["id"],
            "status": email["status"],
            "defect_fields": sorted(email.get("defect_fields") or []),
        }

    (out / KEY).write_text(json.dumps(key, indent=2), encoding="utf-8")

    with (out / SHEET).open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["pair", "seconds", "verdict", "fields_that_differ", "who"])
        for number in sorted(key):
            writer.writerow([number, "", "", "", ""])

    print(f"  packet written to {out}/")
    print(f"  {len(chosen)} pairs: " + ", ".join(f"{k}x{v}" for k, v in SAMPLE.items()))
    print()
    print("  Give the reader ONLY the numbered folders. The answers are in "
          f"{KEY}, which they must not see.")
    print("  For each pair they write, in " + SHEET + ":")
    print("    seconds             stopwatch, from opening the pair to writing a verdict")
    print("    verdict             OK, MISMATCH or NEEDS_REVIEW")
    print("    fields_that_differ  semicolon separated, blank when the verdict is OK")
    print("                        one of: " + ", ".join(FIELDS))
    print("    who                 their name, so several people can share one sheet")

    return 0


def normalise(text: str) -> set[str]:
    return {part.strip().lower() for part in text.split(";") if part.strip()}


def score(folder: Path) -> int:
    key = json.loads((folder / KEY).read_text(encoding="utf-8"))
    rows = list(csv.DictReader((folder / SHEET).open(encoding="utf-8")))
    done = [r for r in rows if (r.get("seconds") or "").strip()]
    if not done:
        raise SystemExit(f"nothing filled in yet in {folder / SHEET}")

    times: list[float] = []
    right_verdict = right_fields = 0
    misses: list[str] = []

    for row in done:
        answer = key.get(row["pair"].strip())
        if not answer:
            continue
        try:
            times.append(float(row["seconds"]))
        except ValueError:
            print(f"  pair {row['pair']}: seconds is not a number, skipped")
            continue

        verdict_ok = row["verdict"].strip().upper() == answer["status"]
        right_verdict += verdict_ok
        theirs = normalise(row.get("fields_that_differ", ""))
        ours = {FIELD_NAMES.get(f, f).lower() for f in answer["defect_fields"]}
        fields_ok = verdict_ok and theirs == ours
        right_fields += fields_ok
        if not fields_ok:
            misses.append(f"    pair {row['pair']} ({answer['email_id']}): "
                          f"said {row['verdict'].strip() or '-'} {sorted(theirs) or ''}, "
                          f"actually {answer['status']} {sorted(ours) or ''}")

    n = len(times)
    print(f"  checks completed      {n}")
    print(f"  average               {statistics.mean(times):.0f} s per pair")
    if n > 1:
        print(f"  range                 {min(times):.0f} s to {max(times):.0f} s")
        print(f"  median                {statistics.median(times):.0f} s")
    print(f"  total time            {sum(times)/60:.1f} minutes")
    print()
    print(f"  verdict correct       {right_verdict} of {n}")
    print(f"  and the exact fields  {right_fields} of {n}")
    if misses:
        print("\n  where it went wrong:")
        print("\n".join(misses))
    print()
    print("  Quote it as: averaged over N checks by M people, with the range.")
    print("  Our side of the comparison is the LIVE path, not a saved result:")
    print("    python3 -m cli.rules_first_check --timed")

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    make = sub.add_parser("build", help="write the packet")
    make.add_argument("--out", default="timed-test")
    rate = sub.add_parser("score", help="score the filled-in sheet")
    rate.add_argument("folder")
    args = parser.parse_args()

    if args.command == "build":
        return build(Path(args.out))

    return score(Path(args.folder))


if __name__ == "__main__":
    sys.exit(main())
