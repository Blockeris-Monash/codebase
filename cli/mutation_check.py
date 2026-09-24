#!/usr/bin/env python3
"""Mutation check: prove the comparison stage detects defects, instead of asserting it.

    python3 -m cli.mutation_check

Takes every email whose saved SI and BL extracts compare as OK, breaks exactly one field of the BL,
and runs the same clean and compare path as POST /extract-clean-compare. A detected defect is a
MISMATCH that names exactly that field. Harmless edits (case, spacing, an absent UN/LOCODE, the same
weight in tonnes) are also applied and must stay OK, so detection is not bought with false alarms.
Offline, no model calls: it reads results/extracts.
"""
from __future__ import annotations

import copy
import re
from collections import defaultdict
from pathlib import Path
from typing import Callable

import backend.app as pipeline
from backend.compare.comparator import CANONICAL_FIELDS, compare
from backend.compare.normalise import NAME_SPLIT

ROOT = Path(__file__).resolve().parents[1]
EXTRACTS = ROOT / "results" / "extracts"

OTHER_NAME = "ZENITH GLOBAL TRADING"


def swap_port(raw: str) -> str:
    return "ROTTERDAM, NETHERLANDS (NLRTM)" if "ROTTERDAM" not in raw.upper() else "ANTWERP, BELGIUM (BEANR)"


def bump_count(raw: str) -> str:
    return re.sub(r"\d+", lambda m: str(int(m.group()) + 1), raw, count=1)


def bump_weight(raw: str) -> str:
    return re.sub(r"[\d,]+(?:\.\d+)?", lambda m: f"{float(m.group().replace(',', '')) + 50:,.2f}", raw, count=1)


def other_name(raw: str) -> str:
    return OTHER_NAME if OTHER_NAME not in raw.upper() else "MERIDIAN EXPORT HOUSE"


def typo_name(raw: str) -> str:
    """Drop one letter from inside the name. (A trailing full stop is stripped by design.)"""
    name = re.split(NAME_SPLIT, raw.strip())[0]
    return name[:1] + name[2:] if len(name) > 3 else name + "X"


DEFECTS: dict[str, list[tuple[str, Callable[[str], str]]]] = {
    "shipper": [("different company", other_name), ("one letter dropped", typo_name)],
    "consignee": [("different company", other_name), ("one letter dropped", typo_name)],
    "notify_party": [("different company", other_name), ("one letter dropped", typo_name)],
    "port_of_loading": [("different port", swap_port)],
    "port_of_discharge": [("different port", swap_port)],
    "container_count": [("count plus one", bump_count)],
    "gross_weight_kg": [("weight plus 50", bump_weight)],
}

HARMLESS: dict[str, list[tuple[str, Callable[[str], str]]]] = {
    "shipper": [("lower case", str.lower), ("padding spaces", lambda r: "  " + r + "  ")],
    "consignee": [("lower case", str.lower)],
    "notify_party": [("lower case", str.lower)],
    "port_of_loading": [("LOCODE removed", lambda r: re.sub(r"\s*\([A-Z0-9]{5}\)", "", r))],
    "port_of_discharge": [("LOCODE removed", lambda r: re.sub(r"\s*\([A-Z0-9]{5}\)", "", r))],
}


def ok_pairs() -> dict[str, tuple[dict, dict]]:
    """Saved SI and BL extracts for every email that compares as OK today."""
    pipeline.EXTRACTS_DIR = EXTRACTS
    pairs = {}
    for si_file in sorted(EXTRACTS.glob("email_*_SI.json")):
        email_id = si_file.name[: -len("_SI.json")]
        si = pipeline.load_saved_extract(email_id, "SI")
        bl = pipeline.load_saved_extract(email_id, "BL")
        if si and bl and run(email_id, si, bl).status == "OK":
            pairs[email_id] = (si, bl)
    return pairs


def run(email_id: str, si: dict, bl: dict):
    si_doc = {**copy.deepcopy(si), "fields": pipeline.apply_cleaner(copy.deepcopy(si["fields"]))}
    bl_doc = {**copy.deepcopy(bl), "fields": pipeline.apply_cleaner(copy.deepcopy(bl["fields"]))}
    return compare(email_id, si_doc, bl_doc)


def mutated(bl: dict, field: str, edit: Callable[[str], str]) -> dict:
    out = copy.deepcopy(bl)
    out["fields"][field]["raw"] = edit(out["fields"][field]["raw"])
    return out


def run_check(pairs: dict[str, tuple[dict, dict]] | None = None) -> dict:
    """Counts per (field, mutation): trials, detected, missed (a list of email ids)."""
    pairs = ok_pairs() if pairs is None else pairs
    defects: dict = defaultdict(lambda: {"trials": 0, "detected": 0, "missed": []})
    harmless: dict = defaultdict(lambda: {"trials": 0, "false_alarms": []})
    for email_id, (si, bl) in pairs.items():
        for field in CANONICAL_FIELDS:
            if not (bl["fields"][field].get("raw") or "").strip():
                continue
            for name, edit in DEFECTS[field]:
                result = run(email_id, si, mutated(bl, field, edit))
                stat = defects[(field, name)]
                stat["trials"] += 1
                if result.status == "MISMATCH" and result.defect_fields == [field]:
                    stat["detected"] += 1
                else:
                    stat["missed"].append(email_id)
            for name, edit in HARMLESS.get(field, []):
                result = run(email_id, si, mutated(bl, field, edit))
                stat = harmless[(field, name)]
                stat["trials"] += 1
                if result.status != "OK":
                    stat["false_alarms"].append(email_id)
    return {"defects": dict(defects), "harmless": dict(harmless), "emails": len(pairs)}


def main() -> None:
    report = run_check()
    print(f"{report['emails']} emails that compare as OK, one field of the BL changed at a time\n")
    print("Defects (must be caught as MISMATCH on exactly that field)")
    for (field, name), s in report["defects"].items():
        print(f"  {field:<18} {name:<20} caught {s['detected']:>3} of {s['trials']:<3} missed {s['missed'][:5]}")
    print("\nHarmless edits (must stay OK)")
    for (field, name), s in report["harmless"].items():
        print(f"  {field:<18} {name:<20} false alarms {len(s['false_alarms']):>3} of {s['trials']:<3} {s['false_alarms'][:5]}")
    trials = sum(s["trials"] for s in report["defects"].values())
    caught = sum(s["detected"] for s in report["defects"].values())
    print(f"\nTotal defects caught: {caught} of {trials}")


if __name__ == "__main__":
    main()
