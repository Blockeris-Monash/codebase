"""PROTOTYPE ONLY. Builds data.js for the UI prototype from real saved results.
Categories for non-comparison emails are a crude keyword guess (Lane B's real classifier is not merged)."""
import json, glob, re, sys
sys.path.insert(0, "/home/kaithod/Hackathon/GitRepo/codebase/tools")
from normalise import compare_row
from contract_types import FIELD_NAMES

ROOT = "/home/kaithod/Hackathon"
INBOX = f"{ROOT}/GitRepo/codebase/data/inbox"
EXT = f"{ROOT}/results/extracts"

def guess(subject, body, has_att):
    s = (subject + " " + body[:300]).lower()
    if re.search(r"bitcoin|exclusive offer|storage is|valued customer|increase your|approval required|prize|winner", s): return "SPAM"
    if re.search(r"invoice|billing|charges|debit note|payment|\bsoa\b", s): return "INVOICE_QUERY"
    if re.search(r"\bsi\b|shipping instruction|bl draft|draft bl", s): return "SI_REQUEST"
    return "GENERAL"

def load(eid, role):
    try: return json.load(open(f"{EXT}/{eid}_{role}.json"))
    except FileNotFoundError: return None

out = []
for f in sorted(glob.glob(f"{INBOX}/*.json")):
    d = json.load(open(f)); eid = d["email_id"]
    body = re.sub(r"\n{3,}", "\n\n", d["body"]).strip()
    e = {"id": eid, "from": d["from"], "subject": d["subject"], "body": body[:700], "n_att": len(d["attachments"])}
    si, bl = load(eid, "SI"), load(eid, "BL")
    if len(d["attachments"]) == 0:
        e["cat"] = guess(d["subject"], body, False)
    elif si and bl:
        e["cat"] = "BL_COMPARISON"
        bad = [x for x in (si, bl) if x["parse_status"] != "ok"]
        wrong = [x for x in (si, bl) if x["parse_status"] == "ok" and x["detected_doc_type"] != x["declared_role"]]
        if bad: e["status"], e["reason"] = "NEEDS_REVIEW", "unreadable"
        elif wrong: e["status"], e["reason"] = "NEEDS_REVIEW", "wrong_doc_type"
        else:
            rows = [compare_row(k, si["fields"][k]["raw"], bl["fields"][k]["raw"]) for k in FIELD_NAMES]
            e["rows"] = rows
            e["docs"] = {}
            for x in (si, bl):
                try: e["docs"][x["declared_role"]] = open(f"{ROOT}/GitRepo/codebase/data/{x['source_path']}", encoding="utf-8").read()
                except (OSError, UnicodeDecodeError): e["docs"][x["declared_role"]] = None
            if any(r["verdict"] == "missing" for r in rows): e["status"], e["reason"] = "NEEDS_REVIEW", "missing_value"
            elif any(r["verdict"] == "mismatch" for r in rows): e["status"] = "MISMATCH"
            else: e["status"] = "OK"
    else:
        e["cat"] = "BL_COMPARISON"; e["status"], e["reason"] = "NEEDS_REVIEW", "missing_attachment"
    out.append(e)
out.sort(key=lambda e: e["id"], reverse=True)   # dataset has no dates; id order stands in for newest first
open(f"{ROOT}/prototype/data.js", "w").write("const EMAILS = " + json.dumps(out, ensure_ascii=False) + ";")
import collections
print(len(out), collections.Counter(e["cat"] for e in out), collections.Counter(e.get("status") for e in out), collections.Counter(e.get("reason") for e in out))
