#!/usr/bin/env python3
"""One command that produces every number quoted on the slides and in the video.

    python3 -m cli.evidence            # writes results/evidence.md
    python3 -m cli.evidence --tests    # also runs the test suite and reports the count

Everything is computed offline from files in the repo, so a judge can rerun it:
  1. Extraction: the saved Qwen extracts against the rules reader, after normalising both.
  2. Detection: the mutation check (one field of a matching BL broken at a time).
  3. Pipeline results: what the review UI shows (frontend/results.js, built by cli.make_results).
  4. Classifier: Qwen's saved categories against the keyword fallback, and against
     results/classifier_handlabels.json when that file exists (labels made by reading the emails).
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

from backend.compare.normalise import normalise
from backend.contracts import FIELD_NAMES
from backend.extract.rules import fields_from_pairs
from backend.read.documents import read_document
from cli import mutation_check
from cli.make_results import fallback_category

ROOT = Path(__file__).resolve().parents[1]


# ---------- 1. extraction: AI against the rules reader ----------

def extraction_agreement(extracts_dir: Path, data_dir: Path) -> dict:
    tally: Counter = Counter()
    per_field: dict = defaultdict(Counter)
    documents = 0
    for file in sorted(extracts_dir.glob("*.json")):
        extract = json.loads(file.read_text(encoding="utf-8"))
        if extract["parse_status"] != "ok":
            continue
        documents += 1
        _, pairs = read_document(data_dir / extract["source_path"])
        rules = fields_from_pairs(pairs)
        for field in FIELD_NAMES:
            ai, by_rules = (normalise(field, extract["fields"][field]["raw"]),
                            normalise(field, rules[field]["raw"]))
            kind = "agree" if ai == by_rules else "ai_only" if by_rules is None else "rules_only" if ai is None else "differ"
            tally[kind] += 1
            per_field[field][kind] += 1
    total = sum(tally.values())
    return {"documents": documents, "fields": total, "tally": dict(tally),
            "agree_share": tally["agree"] / total if total else 0.0,
            "per_field": {f: dict(c) for f, c in per_field.items()}}


# ---------- 3. pipeline results ----------

def pipeline_summary(results: list[dict]) -> dict:
    checked = [e for e in results if e.get("status")]
    status = Counter(e["status"] for e in checked)
    return {
        "emails": len(results),
        "with_attachments": sum(1 for e in results if e.get("n_attachments")),
        "categories": dict(Counter(e["category"] for e in results)),
        "comparisons": len(checked),
        "status": dict(status),
        "reasons": dict(Counter(e["review_reason"] for e in checked if e["status"] == "NEEDS_REVIEW")),
        "defect_fields": dict(Counter(f for e in checked if e["status"] == "MISMATCH" for f in e["defect_fields"])),
        "auto_cleared_share": status["OK"] / len(checked) if checked else 0.0,
        "flagged": status["MISMATCH"] + status["NEEDS_REVIEW"],
    }


# ---------- 4. classifier ----------

def classifier_summary(classified: dict, emails: dict) -> dict:
    disagreements = []
    for email_id, saved in sorted(classified.items()):
        record = emails[email_id]
        fallback = fallback_category(record["subject"], record["body"], len(record["attachments"]))
        if saved["category"] != fallback:
            disagreements.append((email_id, saved["category"], fallback))
    return {"total": len(classified),
            "categories": dict(Counter(c["category"] for c in classified.values())),
            "low_confidence": sum(1 for c in classified.values() if c["confidence"] < 0.85),
            "agree_with_fallback": len(classified) - len(disagreements),
            "disagreements": disagreements}


UNDECIDED = "AMBIGUOUS"  # a label the team has not ruled on yet, left out of the accuracy


def hand_label_accuracy(classified: dict, labels: dict) -> dict:
    labels = {i: c for i, c in labels.items() if i.startswith("email_")}
    both = sorted(set(classified) & set(labels))
    decided = [i for i in both if labels[i] != UNDECIDED]
    wrong = [(i, classified[i]["category"], labels[i]) for i in decided if classified[i]["category"] != labels[i]]
    return {"labelled": len(decided), "correct": len(decided) - len(wrong),
            "ambiguous": len(both) - len(decided), "wrong": wrong}


# ---------- report ----------

def pct(part: float, whole: float) -> str:
    return f"{100 * part / whole:.1f}%" if whole else "n/a"


def load_results_js(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8")
    return json.loads(text[text.index("["): text.rindex("]") + 1])


def load_json_dir(directory: Path) -> dict:
    return {f.stem: json.loads(f.read_text(encoding="utf-8")) for f in sorted(directory.glob("email_*.json"))}


def test_count() -> str:
    run = subprocess.run([sys.executable, "-m", "pytest", "-q"], cwd=ROOT, capture_output=True, text=True)
    last = run.stdout.strip().splitlines()[-1] if run.stdout.strip() else "no output"
    return re.sub(r"\s+in [\d.]+s.*", "", last)


def render(report: dict) -> str:
    out = ["# Ship Happens: evidence", "", "Every number below is computed by `python3 -m cli.evidence` from files in this repo.", ""]
    ext = report["extraction"]
    out += ["## 1. Extraction: AI against an independent rules reader",
            f"- {ext['documents']} documents, {ext['fields']} fields compared after normalising both sides.",
            f"- Agree: {ext['tally'].get('agree', 0)} ({pct(ext['tally'].get('agree', 0), ext['fields'])}). "
            f"Conflicting values: {ext['tally'].get('differ', 0)}. "
            f"AI only: {ext['tally'].get('ai_only', 0)}. Rules only: {ext['tally'].get('rules_only', 0)}.",
            "- Agreement does not prove both are right, so the hand check (see results/validation-summary.md) reads the source files.", ""]
    mut = report["mutation"]
    trials = sum(s["trials"] for s in mut["defects"].values())
    caught = sum(s["detected"] for s in mut["defects"].values())
    harmless = sum(s["trials"] for s in mut["harmless"].values())
    alarms = sum(len(s["false_alarms"]) for s in mut["harmless"].values())
    out += ["## 2. Detection: injected defects",
            f"- {mut['emails']} emails that compare as OK; one field of the BL broken at a time.",
            f"- Defects caught on exactly the changed field: {caught} of {trials}.",
            f"- Harmless edits (case, padding, missing UN/LOCODE) that wrongly raised a flag: {alarms} of {harmless}.", ""]
    pipe = report["pipeline"]
    out += ["## 3. What the review UI shows",
            f"- {pipe['emails']} emails, {pipe['with_attachments']} with attachments, {pipe['comparisons']} compared SI against BL.",
            f"- Match {pipe['status'].get('OK', 0)}, Mismatch {pipe['status'].get('MISMATCH', 0)}, "
            f"Needs review {pipe['status'].get('NEEDS_REVIEW', 0)}.",
            f"- Cleared with no human action: {pct(pipe['status'].get('OK', 0), pipe['comparisons'])}. "
            f"Flagged for a person: {pipe['flagged']}.",
            f"- Fields that differ in the mismatches: {', '.join(f'{k} {v}' for k, v in sorted(pipe['defect_fields'].items(), key=lambda kv: -kv[1])) or 'none'}.",
            f"- Reasons for review: {', '.join(f'{k} {v}' for k, v in sorted(pipe['reasons'].items(), key=lambda kv: -kv[1])) or 'none'}.",
            f"- Categories: {', '.join(f'{k} {v}' for k, v in sorted(pipe['categories'].items(), key=lambda kv: -kv[1]))}.", ""]
    cls = report.get("classifier")
    if cls:
        out += ["## 4. Classifier (Qwen)",
                f"- {cls['total']} emails classified: {', '.join(f'{k} {v}' for k, v in sorted(cls['categories'].items(), key=lambda kv: -kv[1]))}.",
                f"- Confidence below 0.85 (worth a second look): {cls['low_confidence']}.",
                f"- Agrees with the plain keyword fallback on {cls['agree_with_fallback']} of {cls['total']} "
                f"({pct(cls['agree_with_fallback'], cls['total'])}); the {len(cls['disagreements'])} others are where the AI adds value or errs."]
        hand = report.get("hand_labels")
        if hand:
            out.append(f"- Against {hand['labelled'] + hand['ambiguous']} emails read and labelled by hand (not looking at the model's answer): "
                       f"{hand['correct']} of {hand['labelled']} correct ({pct(hand['correct'], hand['labelled'])}). "
                       f"{hand['ambiguous']} left out: send-the-draft-BL emails with no attachment, which the team has not ruled on.")
            out += [f"  - wrong: {i}: model {m}, label {l}" for i, m, l in hand["wrong"]]
        out.append("")
    if report.get("tests"):
        out += ["## 5. Tests", f"- {report['tests']}", ""]
    out += ["## Estimate, not a measurement",
            "- Time saved is only an estimate: multiply the number of SI vs BL checks by the minutes a person takes to compare two documents by hand. State that assumption wherever the figure is used.", ""]
    return "\n".join(out)


def build_report(args: argparse.Namespace) -> dict:
    data = Path(args.data)
    report = {"extraction": extraction_agreement(Path(args.extracts), data),
              "mutation": mutation_check.run_check(),
              "pipeline": pipeline_summary(load_results_js(Path(args.results)))}
    saved = Path(args.classifications)
    if saved.exists() and any(saved.glob("email_*.json")):
        classified = load_json_dir(saved)
        emails = load_json_dir(data / "inbox")
        report["classifier"] = classifier_summary(classified, emails)
        labels = Path(args.labels)
        if labels.exists():
            report["hand_labels"] = hand_label_accuracy(classified, json.loads(labels.read_text(encoding="utf-8")))
    if args.tests:
        report["tests"] = test_count()
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--data", default=str(ROOT / "data"))
    parser.add_argument("--extracts", default=str(ROOT / "results" / "extracts"))
    parser.add_argument("--classifications", default=str(ROOT / "results" / "classifications"))
    parser.add_argument("--results", default=str(ROOT / "frontend" / "results.js"))
    parser.add_argument("--labels", default=str(ROOT / "results" / "classifier_handlabels.json"))
    parser.add_argument("--out", default=str(ROOT / "results" / "evidence.md"))
    parser.add_argument("--tests", action="store_true", help="also run the test suite and report the count")
    args = parser.parse_args()

    text = render(build_report(args))
    Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
