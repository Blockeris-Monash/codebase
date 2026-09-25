"""A reviewer can confirm, dismiss or fix a field the check flagged, and the admin hears of every change.

Confirm difference: the check was right, nothing changes. Not a real difference: the field counts as a
match. Fix the reading: the AI misread one document, so the reviewer types what it says and the backend
compares that field again with the same rules as the full check (POST /recompare, no model).

The email's status, folder, counts and reply draft then follow the corrected fields, while "How Ship
Happens decided" still shows what the pipeline did. A dismiss or a fix (or undoing one) files a human
report to the admin queue; a plain confirm does not, because nothing on screen changed.

The page logic is run for real in node on the saved results, using the page's own functions.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend import app as app_module

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
INDEX = (FRONTEND / "index.html").read_text(encoding="utf-8")
SCRIPT = INDEX[INDEX.index("<script>\n"):]
STORE = (FRONTEND / "store.js").read_text(encoding="utf-8")
MIGRATION = (ROOT / "backend" / "db" / "migrations" / "0007_correction_kind.sql").read_text(encoding="utf-8")
RESULTS_JS = (FRONTEND / "results.js").read_text(encoding="utf-8")
RESULTS = json.loads(RESULTS_JS[RESULTS_JS.index("["):RESULTS_JS.rindex("]") + 1])
BY_ID = {e["id"]: e for e in RESULTS}

ONE_DIFFERENCE = "email_499"    # gross weight: SI 40,326 KG, BL 41,326 KG
TWO_DIFFERENCES = "email_468"
ONE_BLANK = "email_520"         # consignee blank on one side


def block(start: str, end: str = "\n}\n") -> str:
    at = SCRIPT.index(start)
    return SCRIPT[at:SCRIPT.index(end, at) + len(end)]


def line(pattern: str) -> str:
    return re.search(pattern + r".*\n", SCRIPT).group(0)


def branch(action: str) -> str:
    lines = [text for text in SCRIPT.splitlines() if f'a==="{action}"' in text]
    assert len(lines) == 1, f"expected one branch for {action!r}, found {len(lines)}"
    return lines[0]


def page(body: str, corr: dict | None = None, user: bool = False) -> object:
    """Run `body` after the page's correction code, on results.js. It prints one JSON value."""
    js = "\n".join([
        RESULTS_JS,
        "const T = s=>s, t = s=>s, render = ()=>{};",
        "const window = {}, localStorage = {setItem(){}, getItem(){ return null; }};",
        f"const S = {{mailbox:'demo', q:'', f:'MISMATCH', sort:'worst', sel:null, marks:{{}}, "
        f"corr:{json.dumps(corr or {})}, rev:null, user:{'{}' if user else 'null'}}};",
        "const byId = Object.fromEntries(RESULTS.map(e=>[e.id,e]));",
        line(r"const FIELDS = "), line(r"const LABEL = "),
        line(r"const rawList = "), line(r"const mailList = "), line(r"const getEmail = "),
        block("function withCorrections(e){"),
        line(r"function saveCorr\(\)"),
        block("function correctionRow("), block("function correctionReport("), block("function keepCorrection("),
        body,
    ])
    out = subprocess.run(["node"], input=js, capture_output=True, text=True, encoding="utf-8", check=True).stdout
    return json.loads(out)


def corrected(email_id: str, corr: dict) -> dict:
    return page(f"console.log(JSON.stringify(withCorrections(getEmail({json.dumps(email_id)}))));",
                corr={email_id: corr})


@pytest.fixture
def client():
    with TestClient(app_module.app) as client:
        yield client


# --- the backend compares one field again ------------------------------------

def test_the_recompare_agrees_with_the_saved_check_on_every_field(client: TestClient) -> None:
    """Unchanged values must get the verdict the full check gave, or a fix would be judged by another rule."""
    rows = [row for email in RESULTS for row in email.get("rows") or []]
    assert len(rows) > 700
    for row in rows:
        answer = client.post("/recompare", json={"field": row["field"], "si_raw": row["si_raw"], "bl_raw": row["bl_raw"]})
        assert answer.status_code == 200
        assert answer.json()["verdict"] == row["verdict"], row


def test_a_fixed_reading_is_compared_again(client: TestClient) -> None:
    fixed = client.post("/recompare", json={"field": "gross_weight_kg", "si_raw": "40,326 KG", "bl_raw": "40,326.00 KGS"})
    assert fixed.json()["verdict"] == "match"
    still = client.post("/recompare", json={"field": "gross_weight_kg", "si_raw": "40,326 KG", "bl_raw": "40,999 KG"})
    assert still.json()["verdict"] == "mismatch"
    blank = client.post("/recompare", json={"field": "consignee", "si_raw": "ACME TRADING SDN BHD", "bl_raw": None})
    assert blank.json()["verdict"] == "missing"


def test_the_recompare_refuses_an_unknown_field_or_an_endless_value(client: TestClient) -> None:
    assert client.post("/recompare", json={"field": "price", "si_raw": "1", "bl_raw": "1"}).status_code == 422
    assert client.post("/recompare", json={"field": "shipper", "si_raw": "x" * 2001, "bl_raw": "x"}).status_code == 422


# --- the page lays the reviewer's call over the check -------------------------

def test_dismissing_the_only_difference_verifies_the_email() -> None:
    email = corrected(ONE_DIFFERENCE, {"gross_weight_kg": {"kind": "dismiss"}})
    assert (email["was_status"], email["status"], email["defect_fields"]) == ("MISMATCH", "OK", [])
    row = next(r for r in email["rows"] if r["field"] == "gross_weight_kg")
    assert row["verdict"] == "match" and row["reviewed"] == "dismiss"


def test_confirming_a_difference_changes_nothing_but_the_tag() -> None:
    email = corrected(ONE_DIFFERENCE, {"gross_weight_kg": {"kind": "confirm"}})
    assert email["status"] == "MISMATCH" and email["defect_fields"] == ["gross_weight_kg"]
    assert next(r for r in email["rows"] if r["field"] == "gross_weight_kg")["reviewed"] == "confirm"


def test_a_fix_takes_the_verdict_the_backend_gave(client: TestClient) -> None:
    row = client.post("/recompare", json={"field": "gross_weight_kg", "si_raw": "40,326 KG", "bl_raw": "40,326 KG"}).json()
    email = corrected(ONE_DIFFERENCE, {"gross_weight_kg": {"kind": "fix", "side": "BL", "row": row}})
    assert email["status"] == "OK"
    fixed = next(r for r in email["rows"] if r["field"] == "gross_weight_kg")
    assert (fixed["bl_raw"], fixed["reviewed"]) == ("40,326 KG", "fix")


def test_one_of_two_differences_dismissed_still_needs_action() -> None:
    first = BY_ID[TWO_DIFFERENCES]["defect_fields"][0]
    email = corrected(TWO_DIFFERENCES, {first: {"kind": "dismiss"}})
    assert email["status"] == "MISMATCH"
    assert email["defect_fields"] == BY_ID[TWO_DIFFERENCES]["defect_fields"][1:]


def test_a_blank_field_filled_in_by_the_reviewer_is_checked(client: TestClient) -> None:
    blank = next(r for r in BY_ID[ONE_BLANK]["rows"] if r["verdict"] == "missing")
    side = "SI" if not blank["si_raw"] else "BL"
    value = blank["bl_raw"] if side == "SI" else blank["si_raw"]
    body = {"field": blank["field"], "si_raw": value if side == "SI" else blank["si_raw"],
            "bl_raw": value if side == "BL" else blank["bl_raw"]}
    row = client.post("/recompare", json=body).json()
    email = corrected(ONE_BLANK, {blank["field"]: {"kind": "fix", "side": side, "row": row}})
    assert (email["was_status"], email["status"], email["review_reason"]) == ("NEEDS_REVIEW", "OK", None)


def test_an_email_without_corrections_is_the_same_object() -> None:
    assert page("const e = getEmail('email_499'); console.log(JSON.stringify(withCorrections(e) === e));") is True


def test_the_folders_follow_the_corrections() -> None:
    counts = page("console.log(JSON.stringify(['MISMATCH','OK'].map(s=>mailList().filter(e=>e.status===s).length)));",
                  corr={ONE_DIFFERENCE: {"gross_weight_kg": {"kind": "dismiss"}}})
    before = [sum(e.get("status") == s for e in RESULTS) for s in ("MISMATCH", "OK")]
    assert counts == [before[0] - 1, before[1] + 1]


def test_a_corrected_email_stays_in_the_list_while_it_is_open() -> None:
    stays = line(r"  const stays = ")
    assert "e.was_status" in stays and "S.marks[e.id]" in stays


# --- what reaches the team ----------------------------------------------------

def calls_for(steps: list[str], user: bool = True) -> dict:
    run = "\n".join([
        "const calls = [];",
        "window.Store = {pushCorrection:(id,row,report)=>{ calls.push({id,row,report}); return Promise.resolve(true); }};",
        f"S.rev = {{id:{json.dumps(ONE_DIFFERENCE)}, field:'gross_weight_kg'}};",
        *steps,
        "console.log(JSON.stringify({calls, corr:S.corr, sent:S.rev.sent}));",
    ])
    return page(run, user=user)


def test_a_confirm_is_kept_but_files_no_report() -> None:
    out = calls_for(["keepCorrection('email_499','gross_weight_kg',{kind:'confirm'});"])
    (call,) = out["calls"]
    assert call["row"] == {"field": "gross_weight_kg", "kind": "confirm", "side": None, "was": "mismatch", "corrected": "mismatch"}
    assert call["report"] is None
    assert out["corr"]["email_499"]["gross_weight_kg"]["kind"] == "confirm"


def test_a_dismiss_tells_the_admin_what_changed() -> None:
    out = calls_for(["keepCorrection('email_499','gross_weight_kg',{kind:'dismiss'});"])
    (call,) = out["calls"]
    assert call["row"]["kind"] == "dismiss" and call["row"]["corrected"] == "match"
    report = call["report"]
    assert "Gross weight" in report["title"] and "email_499" in report["title"] and "not a real difference" in report["title"]
    assert "40,326 KG" in report["detail"] and "41,326 KG" in report["detail"]
    assert "Action required -> Verified" in report["detail"]
    assert report["context"]["correction"] == {"field": "gross_weight_kg", "kind": "dismiss", "side": None, "undone": False,
                                               "status_before": "MISMATCH", "status_after": "OK"}


def test_a_fix_tells_the_admin_the_old_and_new_reading() -> None:
    fix = ("keepCorrection('email_499','gross_weight_kg',{kind:'fix', side:'BL', row:{field:'gross_weight_kg', "
           "si_raw:'40,326 KG', bl_raw:'40,326 KG', si_norm:'40326.0', bl_norm:'40326.0', verdict:'match'}});")
    (call,) = calls_for([fix])["calls"]
    assert call["row"] == {"field": "gross_weight_kg", "kind": "fix", "side": "BL", "was": "41,326 KG", "corrected": "40,326 KG"}
    assert "fixed the draft Bill of Lading's Gross weight" in call["report"]["title"]
    assert "read the draft Bill of Lading as: 41,326 KG" in call["report"]["detail"]
    assert "corrected it to: 40,326 KG" in call["report"]["detail"]


def test_undoing_a_change_is_reported_too() -> None:
    out = calls_for(["keepCorrection('email_499','gross_weight_kg',{kind:'dismiss'});",
                     "keepCorrection('email_499','gross_weight_kg',null);"])
    undo = out["calls"][1]
    assert undo["row"] == {"field": "gross_weight_kg", "kind": "undo", "side": None, "was": "dismiss", "corrected": None}
    assert "undid" in undo["report"]["title"] and "Verified -> Action required" in undo["report"]["detail"]
    assert out["corr"] == {}, "an email with nothing corrected must not keep an empty entry"


def test_undoing_a_confirm_files_no_report() -> None:
    out = calls_for(["keepCorrection('email_499','gross_weight_kg',{kind:'confirm'});",
                     "keepCorrection('email_499','gross_weight_kg',null);"])
    assert [c["report"] for c in out["calls"]] == [None, None]


def test_signed_out_the_reviewer_is_told_it_stayed_on_this_device() -> None:
    assert calls_for(["keepCorrection('email_499','gross_weight_kg',{kind:'dismiss'});"], user=False)["sent"] == "local"
    assert calls_for(["keepCorrection('email_499','gross_weight_kg',{kind:'dismiss'});"], user=True)["sent"] == "sending"


def test_the_report_is_filed_as_the_signed_in_reviewer_and_checked() -> None:
    push = STORE[STORE.index("async function pushCorrection("):STORE.index("// --- the reports queue")]
    assert 'kind: "human"' in push and "user_id: u.id" in push, "0006 refuses a report that does not name its author"
    assert push.index('from("reports")') < push.index('from("corrections")'), \
        "the report must not wait on the corrections table"
    assert push.count("checked(await") >= 3, "supabase-js resolves an error, it does not throw"
    assert "mark:" not in push, "correcting a field must not mark the email as done"
    assert "pushCorrection" in STORE[STORE.index("window.Store = {"):]


def pushed(report: bool = True, refuse: tuple[str, ...] = (), signed_in: bool = True) -> dict:
    """Run store.js's pushCorrection against a fake Supabase client that records every write."""
    who = '{id: "user-1"}' if signed_in else "null"
    filed = '{title: "t", detail: "d", context: {correction: {kind: "dismiss"}}}' if report else "null"
    js = "\n".join([
        f"const refuse = new Set({json.dumps(list(refuse))}), writes = [];",
        "const answer = table => ({error: refuse.has(table) ? {message: 'refused'} : null});",
        "const from = table => ({",
        "  upsert: (row, opts) => { writes.push({table, op: 'upsert', row, opts});",
        "    return {select: () => ({single: async () => ({data: {id: 'review-1'}, ...answer(table)})})}; },",
        "  insert: async row => { writes.push({table, op: 'insert', row}); return answer(table); },",
        "});",
        f"const user = {who};",
        "globalThis.window = {SUPABASE_URL: 'https://example.supabase.co', SUPABASE_ANON_KEY: 'sb_publishable_x',",
        "  supabase: {createClient: () => ({from, auth: {getUser: async () => ({data: {user}})}})}};",
        "console.warn = () => {};",
        STORE,
        "const row = {field: 'gross_weight_kg', kind: 'dismiss', side: null, was: 'mismatch', corrected: 'match'};",
        f"const report = {filed};",
        "window.Store.pushCorrection('email_499', row, report).then(ok => console.log(JSON.stringify({ok, writes})));",
    ])
    out = subprocess.run(["node"], input=js, capture_output=True, text=True, encoding="utf-8", check=True).stdout
    return json.loads(out)


def test_signed_in_the_report_and_the_correction_both_land() -> None:
    out = pushed()
    assert out["ok"] is True
    assert [(w["table"], w["op"]) for w in out["writes"]] == [("reports", "insert"), ("reviews", "upsert"), ("corrections", "insert")]
    report, review, correction = (w["row"] for w in out["writes"])
    assert report == {"user_id": "user-1", "kind": "human", "email_ref": "email_499", "title": "t", "detail": "d",
                      "context": {"correction": {"kind": "dismiss"}}}
    assert "mark" not in review
    assert correction == {"review_id": "review-1", "field": "gross_weight_kg", "kind": "dismiss", "side": None,
                          "was": "mismatch", "corrected": "match"}


def test_a_refused_correction_still_reaches_the_admin_but_is_not_called_sent() -> None:
    """Before migration 0007 is run, the corrections table refuses `kind` and `side`."""
    out = pushed(refuse=("corrections",))
    assert out["ok"] is False
    assert out["writes"][0]["table"] == "reports"


def test_a_refused_report_is_not_called_sent_either() -> None:
    out = pushed(refuse=("reports",))
    assert out["ok"] is False
    assert [w["table"] for w in out["writes"]] == ["reports", "reviews", "corrections"]


def test_a_confirm_writes_no_report() -> None:
    out = pushed(report=False)
    assert out["ok"] is True and [w["table"] for w in out["writes"]] == ["reviews", "corrections"]


def test_signed_out_nothing_is_written() -> None:
    assert pushed(signed_in=False) == {"ok": False, "writes": []}


def test_the_migration_allows_every_kind_the_page_sends() -> None:
    kinds = set(re.findall(r"'(\w+)'", re.search(r"check \(kind in \(([^)]*)\)\)", MIGRATION).group(1)))
    assert kinds == {"confirm", "dismiss", "fix", "undo"}
    assert "add column if not exists side" in MIGRATION and "'SI', 'BL'" in MIGRATION
    sent = set(re.findall(r'data-a="corr" data-k="(\w+)"', SCRIPT)) | {"undo"}
    assert sent <= kinds


# --- the screen ---------------------------------------------------------------

def test_only_a_flagged_or_reviewed_field_has_a_review_button() -> None:
    js = "\n".join([
        RESULTS_JS,
        "const t = s=>s, T = s=>s, fld = f=>f, esc = s=>String(s??''), ICON = {MISMATCH:'', GAP:''}, S = {hl:null};",
        line(r"const REVIEWED = "),
        block("function rowsHTML(rows){"),
        f"const rows = RESULTS.find(e=>e.id==={json.dumps(ONE_DIFFERENCE)}).rows;",
        "console.log(JSON.stringify([rowsHTML(rows), rowsHTML(rows.map(r=>({...r, verdict:'match', reviewed:r.verdict!=='match'?'dismiss':undefined})))]));",
    ])
    flagged, reviewed = json.loads(subprocess.run(["node"], input=js, capture_output=True, text=True,
                                                  encoding="utf-8", check=True).stdout)
    assert flagged.count('data-a="rev"') == 1 and 'data-k="gross_weight_kg"' in flagged
    assert reviewed.count('data-a="rev"') == 1 and "Dismissed by you" in reviewed


def test_the_panel_offers_the_three_calls() -> None:
    panel = block("function reviewHTML(e, view){")
    for label in ("Confirm difference", "Not a real difference", "Fix the reading", "Check again", "Undo"):
        assert f't("{label}")' in panel, label
    assert 'data-a="corr" data-k="confirm"' in panel and 'data-a="corr" data-k="dismiss"' in panel
    assert 'data-a="corr" data-k="fix"' in panel and 'data-a="uncorr"' in panel


def test_the_detail_shows_the_corrected_view_but_explains_the_original() -> None:
    detail = block("function detail(e){")
    assert "const view = withCorrections(e);" in detail
    assert "${how(e)}" in detail, "How Ship Happens decided must describe what the pipeline did"
    assert "reviewHTML(e, view)" in detail


def test_the_reply_asks_only_about_what_is_still_wrong() -> None:
    assert "draftFor(withCorrections(getEmail(id)))" in branch("draft")
    first, second = BY_ID[TWO_DIFFERENCES]["defect_fields"]
    js = "\n".join([
        RESULTS_JS,
        "const T = s=>s;",
        f"const S = {{corr:{json.dumps({TWO_DIFFERENCES: {first: {'kind': 'dismiss'}}})}}};",
        line(r"const FIELDS = "), line(r"const line = r=>"),
        block("function withCorrections(e){"), block("function draftFor(e){"),
        f"const e = withCorrections(RESULTS.find(e=>e.id==={json.dumps(TWO_DIFFERENCES)}));",
        "console.log(JSON.stringify({body: draftFor(e).body, names: FIELDS}));",
    ])
    out = json.loads(subprocess.run(["node"], input=js, capture_output=True, text=True, encoding="utf-8", check=True).stdout)
    body, names = out["body"], out["names"]
    assert f"- {names[second]}:" in body and f"- {names[first]}:" not in body
    assert "found a difference" in body


def test_the_recompare_goes_to_the_backend_and_says_when_it_cannot() -> None:
    recompare = block("async function recompareField(){")
    assert 'API_BASE + "/recompare"' in recompare
    assert "Could not reach the checker" in recompare
    assert "keepCorrection(" in recompare
