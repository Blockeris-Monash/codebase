# Data contracts

Five shapes pass between pipeline stages. Everyone builds against these, not
against each other's code.

Each contract is a **JSON Schema file** in `contracts/` — that is the
authoritative definition. This document explains them; the schema enforces
them. A worked example of each lives in `fixtures/`, generated from real
emails by `tools/MakeFixtures.py`.

```
contracts/01-EmailRecord.schema.json
contracts/02-ClassificationResult.schema.json
contracts/03-DocumentExtract.schema.json
contracts/04-ComparisonResult.schema.json
contracts/05-SubmissionEntry.schema.json
```

Numbered in pipeline order, and each file opens with a line saying which
stage it is and who hands it to whom. Refer to them by plain name — the
tooling ignores the prefix:

```bash
python3 tools/ValidateContracts.py out.json DocumentExtract
```

Check anything against them before you hand it downstream:

```bash
python3 tools/ValidateContracts.py                      # every fixture
python3 tools/ValidateContracts.py out.json ComparisonResult   # your output
```

Exits non-zero on a violation, so it drops into CI or a pre-commit hook. No
third-party dependency — every stage can run it.

Owner: R1. Changes go through R1 so nobody's stage breaks silently.

```
Inbox ──1── Classify ──2── Extract ──3── Compare ──4── Report
                                                 └──5── submission.json
```

| # | Contract | Produced by | Consumed by |
|---|---|---|---|
| 1 | `EmailRecord` | loader (R1) | classify (R2) |
| 2 | `ClassificationResult` | classify (R2) | R1, R3 |
| 3 | `DocumentExtract` | extract (R2) | compare (R3) |
| 4 | `ComparisonResult` | compare (R3) | report UI (R5), R1 |
| 5 | `SubmissionEntry` | R1 | `POST /submit` |

Only `BL_COMPARISON` emails reach contracts 3 and 4. Every email gets 1, 2 and 5.

---

## 1 · EmailRecord

Loader output, one per email. `sender_domain` is split out because it is the
single strongest spam signal. `declared_role` is what the *filename* claims —
it is wrong on emails 501–505, so never trust it without checking contract 3's
`detected_doc_type`.

```json
{
  "email_id": "email_004",
  "from": "docs@vitalsolutions.sg",
  "sender_domain": "vitalsolutions.sg",
  "subject": "REQUEST BL DRAFT _ PO 26067_ COATED IVORY BOARD__138MT",
  "body": "Hi Mitchelle,\n\nAttached are the SI and draft BL ...",
  "attachments": [
    { "path": "attachments/email_004_SI.txt", "declared_role": "SI", "format": "txt" },
    { "path": "attachments/email_004_BL.txt", "declared_role": "BL", "format": "txt" }
  ]
}
```

`format` is one of `txt` `pdf` `docx` `xlsx`. `attachments` may be empty.

## 2 · ClassificationResult

One per email, all 520. `decided_by` is read by the official scorer, which
reports the share of decisions made by rule rather than by model — so fill it
in honestly. `evidence` is what the review UI shows a human.

```json
{
  "email_id": "email_004",
  "category": "BL_COMPARISON",
  "decided_by": "rule",
  "confidence": 1.0,
  "evidence": "body: 'Attached are the SI and draft BL'"
}
```

`category` ∈ `BL_COMPARISON` `SI_REQUEST` `INVOICE_QUERY` `GENERAL` `SPAM`.
`decided_by` ∈ `rule` `llm`.

## 3 · DocumentExtract

One per attachment, so a normal comparison email yields two. Keeping `raw`
alongside the field name is what lets the UI show source evidence and lets R3
debug a bad parse without reopening the file.

```json
{
  "email_id": "email_004",
  "declared_role": "SI",
  "source_path": "attachments/email_004_SI.txt",
  "format": "txt",
  "detected_doc_type": "SI",
  "parse_status": "ok",
  "fields": {
    "consignee": {
      "present": true,
      "label_seen": "Consignee (Non-Negotiable)",
      "raw": "EAST BRIGHT FZ-LLC"
    }
  }
}
```

`parse_status` ∈ `ok` `unreadable` `missing` `not_attempted`.
`detected_doc_type` comes from the document's own header, not the filename.
All seven field keys are always present; `present: false` means not found.

## 4 · ComparisonResult

The seven-row table. This is both the report UI's input and the source of
contract 5. `rows` is empty only when nothing was comparable at all.

```json
{
  "email_id": "email_004",
  "status": "MISMATCH",
  "review_reason": null,
  "rows": [
    { "field": "consignee",
      "si_raw": "EAST BRIGHT FZ-LLC", "bl_raw": "UAB NOVAKOPA",
      "si_norm": "EAST BRIGHT FZ-LLC", "bl_norm": "UAB NOVAKOPA",
      "verdict": "mismatch" }
  ],
  "defect_fields": ["consignee", "notify_party"],
  "evidence": "differs after normalisation: consignee, notify_party"
}
```

`status` ∈ `OK` `MISMATCH` `NEEDS_REVIEW`.
`review_reason` ∈ `null` `wrong_doc_type` `missing_attachment` `unreadable` `missing_value`.
`verdict` ∈ `match` `mismatch` `missing`.

Both `si_raw` and `si_norm` are kept: the UI shows `raw`, the verdict uses
`norm`, and showing both is how a reviewer sees *why* something was flagged.

## 5 · SubmissionEntry

Exactly the `sample_submission.json` shape. All 520 ids must be present.

```json
{
  "category": "BL_COMPARISON",
  "status": "MISMATCH",
  "review_reason": null,
  "has_defect": true,
  "defect_fields": ["consignee", "notify_party"]
}
```

`has_defect` is true if and only if `status == "MISMATCH"`.
Non-comparison categories carry `status: "OK"`, no defects.

---

## Fixtures

```
fixtures/01-Ok.json                     email_001  all seven match
fixtures/02-SendDraftBlUnresolved.json  email_003  CATEGORY UNDECIDED - see below
fixtures/03-Mismatch.json               email_004  consignee + notify_party
fixtures/04-SiRequest.json              email_007  classified, stops
fixtures/05-Spam.json                   email_015  classified, stops
fixtures/06-ReviewWrongDoc.json         email_501  BL is a commercial invoice
fixtures/07-ReviewMissingAtt.json       email_506  body says compare, nothing attached
fixtures/08-ReviewUnreadable.json       email_511  corrupt PDF
fixtures/09-ReviewMissingVal.json       email_516  SI gross weight is "N/A"
fixtures/SubmissionSample.json          all nine, in contract-5 shape
```

Numbered by email id, so the five ordinary emails come first and the 5xx
edge cases last.

Every fixture opens with a `_why` block explaining itself:

| key | what it holds |
|---|---|
| `why_chosen` | why this email and not another |
| `covers` | the behaviour or trap under test |
| `assert_this` | what a test should actually check |
| `caveat` | what is our inference rather than an organiser ruling |

Read `_why` before building against a fixture. `caveat` is the important one
— it marks where we guessed.

`02-SendDraftBlUnresolved` is deliberately not buildable. 91 emails (17.5% of the
inbox) say *"Please assist to send the draft BL for X for checking asap"*, and
nothing in the brief says whether they are `SI_REQUEST` or `GENERAL`. Its
category is a placeholder so the file validates. Do not write a test against
it until `#faq` answers.

Each file carries every stage artefact for that email, so any stage can be
built and tested in isolation. Regenerate and re-check with:

```bash
python3 tools/MakeFixtures.py --data ../ --out fixtures
python3 tools/ValidateContracts.py
```

The fixtures are validated against the schemas, so the two cannot drift
apart — a fixture that stops matching its contract fails the check.
