#!/usr/bin/env python3
"""Run the AI extractor over every SI and BL attachment and save one DocumentExtract JSON each.

    python3 -m backend.extract.batch --data data --out results/extracts --model qwen

A rerun skips saved results, and retries any document the model failed on.
"""
from __future__ import annotations

import argparse
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from backend.contracts import DocumentExtract, FIELD_NAMES, ParseStatusType
from backend.extract.ai import AiExtractor
from backend.read.labels import detect_doc_type
from backend.read.documents import document_title, read_document

ATTACHMENT_NAME = re.compile(r"^(?P<email_id>email_\d+)_(?P<role>SI|BL)\.(?P<format>\w+)$")


def absent_fields() -> dict:
    return {f: {"present": False, "label_seen": None, "raw": None} for f in FIELD_NAMES}


def extract_attachment(path: Path, extractor: AiExtractor) -> DocumentExtract | None:
    """The DocumentExtract for one attachment, or None if the model never answered."""
    name = ATTACHMENT_NAME.match(path.name)
    assert name, f"not an SI or BL attachment: {path.name}"
    result: DocumentExtract = {
        "email_id": name["email_id"], "declared_role": name["role"],
        "source_path": f"attachments/{path.name}", "format": name["format"].lower(),
        "detected_doc_type": None, "parse_status": ParseStatusType.NotAttempted,
        "fields": absent_fields()}

    status, pairs = read_document(path)
    if status != ParseStatusType.Ok:
        return {**result, "parse_status": status}

    fields = extractor.extract_fields(name["email_id"], pairs)
    if fields is None:
        return None

    return {**result, "detected_doc_type": detect_doc_type(document_title(path) or ""),
            "parse_status": ParseStatusType.Ok, "fields": fields}


def run_batch(attachments_dir: Path, out_dir: Path, extractor: AiExtractor,
              log=print, workers: int = 1) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    summary: dict = {"done": 0, "skipped": 0, "failed": []}
    paths = [p for p in sorted(attachments_dir.iterdir()) if ATTACHMENT_NAME.match(p.name)]
    todo = [p for p in paths if not (out_dir / f"{p.stem}.json").exists()]
    summary["skipped"] = len(paths) - len(todo)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        jobs = {pool.submit(extract_attachment, path, extractor): path for path in todo}
        for number, job in enumerate(as_completed(jobs), 1):
            path = jobs[job]
            result = job.result()
            if result is None:
                summary["failed"].append(path.name)
                log(f"[{number}/{len(todo)}] {path.name}: model did not answer")
                continue

            (out_dir / f"{path.stem}.json").write_text(
                json.dumps(result, indent=2, ensure_ascii=False))
            summary["done"] += 1
            log(f"[{number}/{len(todo)}] {path.name}: {result['parse_status']}")

    summary["failed"].sort()

    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--data", default=str(Path(__file__).resolve().parents[1] / "data"))
    parser.add_argument("--out", required=True)
    parser.add_argument("--model", choices=("qwen", "gemini"), default="qwen")
    parser.add_argument("--workers", type=int, default=4, help="documents sent at the same time")
    args = parser.parse_args()

    if args.model == "qwen":
        from backend.extract.qwen import qwen_model as model
    else:
        from backend.extract.gemini import gemini_model as model

    summary = run_batch(Path(args.data) / "attachments", Path(args.out), AiExtractor(model),
                        workers=args.workers)
    print(f"done {summary['done']}, skipped {summary['skipped']}, failed {len(summary['failed'])}")
    for name in summary["failed"]:
        print("  failed:", name)

    return 1 if summary["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
