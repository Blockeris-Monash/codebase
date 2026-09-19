#!/usr/bin/env python3
"""Generate stage fixtures from the real dataset.

Every fixture is built from an actual email so downstream stages are tested
against the data's real shape, not an invented one. Re-run after the dataset
changes:  python3 tools/MakeFixtures.py --data ../ --out fixtures
"""
import argparse
import json
import os
import re
from pathlib import Path

SI = "SI"
BL = "BL"
FIELDS = ["shipper", "consignee", "notify_party", "port_of_loading",
          "port_of_discharge", "container_count", "gross_weight_kg"]

# Label variants observed across the corpus, aligned by meaning not by text.
LABELS = {
    "shipper": [r"^shipper(/exporter)?( \(principal or seller\))?$"],
    "consignee": [r"^consignee( \(non-negotiable\))?$", r"^to the order of$"],
    "notify_party": [r"^notify( party)?$", r"^notify party/intermediate consignee$"],
    "port_of_loading": [r"^port of loading( \(pol\))?$", r"^load port$", r"^pol$"],
    "port_of_discharge": [r"^port of discharge( \(pod\))?$", r"^discharge port$", r"^pod$"],
    "container_count": [r"^(total )?containers?( count)?$",
                        r"^no\. of containers( or packages)?$"],
    "gross_weight_kg": [r"^gross wt \(kgs\)$", r"^gross weight ?\(?kgs?\)?$",
                        r"^gross weight$"],
}
DOC_HEADERS = {"SHIPPING INSTRUCTION": SI, "BILL OF LADING (DRAFT)": BL}
CJK = r"[一-鿿]"


def canonical_field(label):
    """Map a document's own label text onto one of the seven field names."""
    plain = re.sub(r"\s+", " ", re.sub(CJK, "", label)).strip().lower()
    plain = re.sub(r"\(\s*\)", "", plain).strip()
    for field, patterns in LABELS.items():
        for pattern in patterns:
            if re.match(pattern, plain):
                return field
    return None


def read_fields(text):
    """Pull the seven fields out of a plain-text SI or BL."""
    found = {}
    for line in text.split("\n"):
        if ":" not in line:
            continue
        label, value = line.split(":", 1)
        field = canonical_field(label)
        if field is None or field in found:
            continue
        found[field] = {"label_seen": label.strip(), "raw": value.strip()}
    return found


def detect_doc_type(text):
    """Read the declared document title. Filenames lie on emails 501-505."""
    header = text.split("\n", 1)[0].strip().upper()
    return DOC_HEADERS.get(header, header or None)


def attachment_meta(path):
    name = os.path.basename(path)
    return {
        "path": path,
        "declared_role": SI if f"_{SI}." in name else BL,
        "format": name.rsplit(".", 1)[-1].lower(),
    }


def email_record(email):
    """Contract 1 — loader output, one per email."""
    return {
        "email_id": email["email_id"],
        "from": email["from"],
        "sender_domain": email["from"].split("@")[-1],
        "subject": email["subject"],
        "body": email["body"],
        "attachments": [attachment_meta(a) for a in email["attachments"]],
    }


def document_extract(data_dir, email_id, meta):
    """Contract 3 — one per attachment. Non-text formats are left unparsed
    here; the extractor owner fills them in with the real parsers."""
    path = Path(data_dir) / meta["path"]
    base = {
        "email_id": email_id,
        "declared_role": meta["declared_role"],
        "source_path": meta["path"],
        "format": meta["format"],
    }
    absent = {f: {"present": False, "label_seen": None, "raw": None} for f in FIELDS}
    if meta["format"] != "txt":
        return {**base, "detected_doc_type": None, "parse_status": "not_attempted",
                "fields": absent}
    text = path.read_text(errors="replace")
    detected = detect_doc_type(text)
    found = read_fields(text)
    fields = {
        f: {
            "present": f in found,
            "label_seen": found.get(f, {}).get("label_seen"),
            "raw": found.get(f, {}).get("raw"),
        }
        for f in FIELDS
    }
    return {**base, "detected_doc_type": detected, "parse_status": "ok",
            "fields": fields}


# --- normalisation ------------------------------------------------------
# Reference implementation only, so fixtures carry realistic normalised
# values. R3 owns the production version and the rules behind it.
LOCODE = re.compile(r"\s*\(([A-Z]{5})\)\s*$")
SENTINEL = re.compile(r"^\s*$|^(n/?a|tba|tbc|-+)$|^_+\s*\w*$", re.I)
NAME_FIELDS = {"shipper", "consignee", "notify_party"}
PORT_FIELDS = {"port_of_loading", "port_of_discharge"}
NAME_SPLIT = r"\s*\|\s*|\s{2,}"


def normalise(field, raw):
    """Return the comparable form, or None when the value is absent."""
    if raw is None:
        return None
    value = re.sub(r"\s+", " ", raw).strip()
    if SENTINEL.match(value):
        return None
    if field in NAME_FIELDS:
        return re.split(NAME_SPLIT, value)[0].upper().strip(" ,")
    if field in PORT_FIELDS:
        return LOCODE.sub("", value).upper().rstrip(",").strip()
    if field == "container_count":
        match = re.match(r"(\d+)", value)
        return match.group(1) if match else None
    if field == "gross_weight_kg":
        match = re.search(r"([\d,]+(?:\.\d+)?)", value)
        return str(float(match.group(1).replace(",", ""))) if match else None
    return value.upper()


MATCH = "match"
MISMATCH = "mismatch"
MISSING = "missing"


def compare_row(field, si_raw, bl_raw):
    si_norm, bl_norm = normalise(field, si_raw), normalise(field, bl_raw)
    if si_norm is None or bl_norm is None:
        verdict = MISSING
    elif si_norm == bl_norm:
        verdict = MATCH
    else:
        verdict = MISMATCH
    return {"field": field, "si_raw": si_raw, "bl_raw": bl_raw,
            "si_norm": si_norm, "bl_norm": bl_norm, "verdict": verdict}


OK, NEEDS_REVIEW = "OK", "NEEDS_REVIEW"
WRONG_DOC_TYPE, MISSING_ATTACHMENT = "wrong_doc_type", "missing_attachment"
UNREADABLE, MISSING_VALUE = "unreadable", "missing_value"
BL_COMPARISON = "BL_COMPARISON"


def comparison_result(email_id, si, bl):
    """Contract 4 — the seven-row table plus the verdict for one email."""
    rows = [compare_row(f, si["fields"][f]["raw"], bl["fields"][f]["raw"])
            for f in FIELDS]
    defects = [r["field"] for r in rows if r["verdict"] == MISMATCH]
    absent = [r["field"] for r in rows if r["verdict"] == MISSING]
    if absent:
        return {"email_id": email_id, "status": NEEDS_REVIEW,
                "review_reason": MISSING_VALUE, "rows": rows, "defect_fields": [],
                "evidence": f"no comparable value on one side for: {', '.join(absent)}"}
    if defects:
        return {"email_id": email_id, "status": "MISMATCH", "review_reason": None,
                "rows": rows, "defect_fields": defects,
                "evidence": f"differs after normalisation: {', '.join(defects)}"}
    return {"email_id": email_id, "status": OK, "review_reason": None,
            "rows": rows, "defect_fields": [],
            "evidence": f"all {len(FIELDS)} fields match after normalisation"}


def review_result(email_id, reason, evidence):
    """Contract 4, escalation form — no table, because nothing was comparable."""
    return {"email_id": email_id, "status": NEEDS_REVIEW, "review_reason": reason,
            "rows": [], "defect_fields": [], "evidence": evidence}


def submission_entry(comparison, category):
    """Contract 5 — exactly the sample_submission.json shape."""
    is_mismatch = comparison["status"] == "MISMATCH"
    return {
        "category": category,
        "status": comparison["status"],
        "review_reason": comparison["review_reason"],
        "has_defect": is_mismatch,
        "defect_fields": comparison["defect_fields"],
    }


def classification(email_id, category, decided_by, evidence, confidence):
    """Contract 2 — one per email. `decided_by` is read by the official
    scorer, which reports the share of decisions made by rule."""
    return {"email_id": email_id, "category": category, "decided_by": decided_by,
            "confidence": confidence, "evidence": evidence}


# Every fixture records WHY it exists, so the next person can tell a
# deliberate choice from an accident. `covers` is the behaviour under test,
# `assert_this` is what a test should check, and `caveat` names anything that
# is our inference rather than an organiser ruling.
SCENARIOS = [
    {
        "name": "Ok", "email_id": "email_001", "category": BL_COMPARISON,
        "decided_by": "rule",
        "classification_evidence": "body: 'Attached are the SI and draft BL'",
        "why_chosen": "A clean baseline. Without one, nothing proves the pipeline "
                      "can say 'nothing wrong here' - and a system that flags "
                      "everything scores badly on defect precision.",
        "covers": "the OK path: all seven fields match, nothing escalates",
        "assert_this": "status == OK, defect_fields == [], seven rows all 'match'",
        "caveat": "We verified the seven fields match. The organisers' own label "
                  "for this email is unknown to us.",
    },
    {
        "name": "Mismatch", "email_id": "email_004", "category": BL_COMPARISON,
        "decided_by": "rule",
        "classification_evidence": "body: 'Attached are the SI and draft BL'",
        "why_chosen": "Matches the shape of the problem statement's own worked "
                      "example - flag only the differing fields and show SI vs BL. "
                      "Two defects, not one, so it tests exact set equality rather "
                      "than a boolean. The consignee NAME changes while the address "
                      "block below it stays identical, which is what forces "
                      "name-only comparison.",
        "covers": "MISMATCH, multi-field, and the name-vs-address distinction",
        "assert_this": "defect_fields is exactly {consignee, notify_party}; the "
                       "other five rows are 'match'. End-to-end credit needs the "
                       "exact set, so a superset scores zero.",
        "caveat": "Our reading of the documents, not an organiser label.",
    },
    {
        "name": "ReviewWrongDoc", "email_id": "email_501", "category": BL_COMPARISON,
        "decided_by": "rule",
        "classification_evidence": "body: 'Attached are the SI and draft BL'",
        "why_chosen": "The file named email_501_BL.txt opens with COMMERCIAL "
                      "INVOICE. This is the only trap where trusting the filename "
                      "produces a confident wrong answer instead of an obvious "
                      "failure - the extractor finds no BL fields and would report "
                      "a false mismatch on all seven.",
        "covers": "document type must be verified from the header before extraction",
        "assert_this": "review_reason == wrong_doc_type, rows == []",
        "caveat": "Emails 501-505 all do this, with invoices, packing lists and "
                  "certificates of origin.",
    },
    {
        "name": "ReviewMissingAtt", "email_id": "email_506", "category": BL_COMPARISON,
        "decided_by": "rule",
        "classification_evidence": "body: 'Please compare the SI and draft BL'",
        "why_chosen": "Zero attachments, but the body says 'Please compare the SI "
                      "and draft BL ... (attachments appear to have been dropped)'. "
                      "It breaks the 'has attachments therefore comparison' "
                      "heuristic in the direction that loses you an email entirely.",
        "covers": "classification cannot gate on attachment presence",
        "assert_this": "category is still BL_COMPARISON despite no attachments; "
                       "review_reason == missing_attachment",
        "caveat": "Emails 507 and 509 are the other shape of this - SI present, "
                  "BL absent. Same reason, different code path.",
    },
    {
        "name": "ReviewUnreadable", "email_id": "email_511", "category": BL_COMPARISON,
        "decided_by": "rule",
        "classification_evidence": "body: 'Attached are the SI and draft BL'",
        "why_chosen": "email_511_BL.pdf is 775 bytes: a %PDF-1.5 header followed by "
                      "random bytes, with no objects at all. A parser must escalate "
                      "rather than crash the run or quietly pass.",
        "covers": "parse failure escalates with a reason",
        "assert_this": "review_reason == unreadable, rows == []",
        "caveat": "KNOWN BUG in this generator: parse_status 'not_attempted' is "
                  "treated as unreadable, so the 13 readable text PDFs would be "
                  "mislabelled too. This fixture is correct, but for a reason that "
                  "will not generalise. Fix before the PDF parser lands.",
    },
    {
        "name": "ReviewMissingVal", "email_id": "email_516", "category": BL_COMPARISON,
        "decided_by": "rule",
        "classification_evidence": "body: 'Attached are the SI and draft BL'",
        "why_chosen": "The ordering trap, and the most valuable fixture here. The "
                      "SI gross weight is 'N/A'. Compare before checking for absent "
                      "values and you emit a false weight mismatch AND a false port "
                      "mismatch on the same email, because the SI port also lacks "
                      "the locode the BL carries.",
        "covers": "sentinel detection must run BEFORE comparison",
        "assert_this": "review_reason == missing_value on gross_weight_kg, and "
                       "port_of_loading is NOT reported as a defect even though the "
                       "raw strings differ",
        "caveat": "Whether a partial comparison should still report the defects it "
                  "did find is a team ruling, not a fact. We chose escalate-whole.",
    },
    {
        "name": "SiRequest", "email_id": "email_007", "category": "SI_REQUEST",
        "decided_by": "rule",
        "classification_evidence": "body: 'Please find Shipping instruction for'",
        "why_chosen": "The largest non-comparison category. The SI data sits inline "
                      "in the email body with no attachment, which tempts an "
                      "extractor into running on something that should have stopped "
                      "at classification.",
        "covers": "the stop path - classified, no comparison performed",
        "assert_this": "ComparisonResult is null; SubmissionEntry status == OK with "
                       "no defects",
        "caveat": "Unambiguous. Not to be confused with the contested bucket below.",
    },
    {
        "name": "SendDraftBlUnresolved", "email_id": "email_003", "category": "SI_REQUEST",
        "decided_by": "rule",
        "classification_evidence": "body: 'Please assist to send the draft BL ... for checking'",
        "why_chosen": "UNRESOLVED - this fixture exists to make the open question "
                      "concrete. 91 emails say 'Please assist to send the draft BL "
                      "for X for checking asap'. They are not comparisons (nothing "
                      "attached), not invoice queries, not spam. Its subject is the "
                      "same TO CONFIRM DOCS family as email_001, which IS a "
                      "comparison - so the subject line cannot separate them.",
        "covers": "the 17.5% of the inbox whose category the brief does not decide",
        "assert_this": "NOTHING YET. Do not build a test on this until #faq answers.",
        "caveat": "The category here is a PLACEHOLDER, set to SI_REQUEST so the "
                  "file validates. It may well be GENERAL. Stage 1 is scored on "
                  "macro-F1, so a wrong call damages two categories at once.",
    },
    {
        "name": "Spam", "email_id": "email_015", "category": "SPAM",
        "decided_by": "rule",
        "classification_evidence": "sender domain crypto-invest.net is on the spam list",
        "why_chosen": "Spam is only 40 emails, but macro-F1 averages the five "
                      "categories equally - so it carries the same weight as the "
                      "129 comparison emails. Cheapest points on the board.",
        "covers": "the spam path, and domain-based classification",
        "assert_this": "category == SPAM, no comparison performed",
        "caveat": "Six sender domains separate spam perfectly here, with no overlap "
                  "with legitimate senders. That rule is brittle if judges test "
                  "with their own data - an open #faq question.",
    },
]


def build(data_dir, email):
    """Return every stage artefact for one email."""
    record = email_record(email)
    extracts = [document_extract(data_dir, email["email_id"], m)
                for m in record["attachments"]]
    by_role = {e["declared_role"]: e for e in extracts}
    si, bl = by_role.get(SI), by_role.get(BL)

    if si is None or bl is None:
        comparison = review_result(email["email_id"], MISSING_ATTACHMENT,
                                   f"expected SI and BL, found {sorted(by_role)}")
    elif bl["parse_status"] != "ok" or si["parse_status"] != "ok":
        comparison = review_result(email["email_id"], UNREADABLE,
                                   "attachment could not be parsed")
    elif bl["detected_doc_type"] != BL or si["detected_doc_type"] != SI:
        comparison = review_result(
            email["email_id"], WRONG_DOC_TYPE,
            f"filename says SI/BL, document header says "
            f"{si['detected_doc_type']}/{bl['detected_doc_type']}")
    else:
        comparison = comparison_result(email["email_id"], si, bl)
    return record, extracts, comparison


REASONING_KEYS = ["why_chosen", "covers", "assert_this", "caveat"]
NON_COMPARISON_ENTRY = {"status": OK, "review_reason": None,
                        "has_defect": False, "defect_fields": []}


def reasoning_block(scenario, email_id):
    """The `_why` header written into every fixture, so the next person can
    tell a deliberate choice from an accident."""
    block = {"scenario": scenario["name"], "email_id": email_id}
    block.update({key: scenario[key] for key in REASONING_KEYS})
    return block


def build_bundle(data_dir, scenario):
    email_id, category = scenario["email_id"], scenario["category"]
    email = json.loads((Path(data_dir) / "inbox" / f"{email_id}.json").read_text())
    record, extracts, comparison = build(data_dir, email)
    is_comparison = category == BL_COMPARISON
    entry = (submission_entry(comparison, category) if is_comparison
             else {"category": category, **NON_COMPARISON_ENTRY})
    bundle = {
        "_why": reasoning_block(scenario, email_id),
        "EmailRecord": record,
        "ClassificationResult": classification(
            email_id, category, scenario["decided_by"],
            scenario["classification_evidence"], 1.0),
        "DocumentExtract": extracts,
        "ComparisonResult": comparison if is_comparison else None,
        "SubmissionEntry": entry,
    }
    return bundle, entry


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="../", help="folder holding inbox/ and attachments/")
    ap.add_argument("--out", default="fixtures")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    submission = {}
    for scenario in SCENARIOS:
        bundle, entry = build_bundle(args.data, scenario)
        submission[scenario["email_id"]] = entry
        (out / f"{scenario['name']}.json").write_text(json.dumps(bundle, indent=2) + "\n")
        print(f"{scenario['name']:24} {scenario['email_id']}  "
              f"{entry['status']:12} {entry['defect_fields']}")
    (out / "SubmissionSample.json").write_text(json.dumps(submission, indent=2) + "\n")
    print(f"\n{len(SCENARIOS)} fixtures + SubmissionSample.json -> {out}/")


if __name__ == "__main__":
    main()
