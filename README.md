# Shipping Document Verification — Averis x Monash Hackathon 2026

Reads a shipping inbox, classifies every email, and for document-comparison
requests checks a draft Bill of Lading against its Shipping Instruction.

## The dataset lives outside this repo

520 emails and 250 attachments are **not committed** — whether the provided
dataset may go in a public repo is an open question with the organisers. The
organiser Docker kit is also kept out, because it contains the answer key.

Expected layout:

```
hackathon/
├── inbox/  attachments/  sample_submission.json   <- dataset, not committed
├── sdoc-hackathon-docker/                         <- answer key, never commit
└── codebase/                                      <- this repo
```

Point the code at the data with `DATA_DIR` (see `.env.example`):

```bash
DATA_DIR=../                        # extracted bundle
DATA_DIR=http://localhost:8081      # local server
```

## Quick start

```bash
# 1. dataset reachable, both ways
python3 tools/SmokeTest.py ../
python3 tools/SmokeTest.py http://localhost:8081

# 2. regenerate stage fixtures from real emails
python3 tools/MakeFixtures.py --data ../ --out fixtures

# 3. check everything still satisfies the contracts
python3 tools/ValidateContracts.py
```

The scoring server runs on **8081**, not 8080 — 8080 is commonly taken. Start
it from the organiser kit with `docker compose up -d`.

## Build against the contracts, not against each other

Five shapes pass between stages, defined as JSON Schema in `contracts/` and
explained in [`docs/00-contracts.md`](docs/00-contracts.md). A worked example
of each is in `fixtures/`. Any stage can be built and tested in isolation
against a fixture — nobody waits on the stage upstream.

```
Inbox ──1── Classify ──2── Extract ──3── Compare ──4── Report
                                                 └──5── submission.json
```

| Area | Owner |
|---|---|
| Pipeline glue, repo, submission, contracts | R1 |
| Classification and field extraction | R2 |
| Normalisation, comparison, self-eval | R3 |
| Docker, cloud, public URL | R4 |
| Report UI, review screen, video | R5 |

## Check your output before handing it on

Write one record to a JSON file and name the contract it should satisfy:

```bash
python3 tools/ValidateContracts.py out.json ComparisonResult
```

Fixtures are numbered by email id — `01-Ok.json` through `09-ReviewMissingVal.json`.

Per stage:

```bash
python3 tools/ValidateContracts.py record.json     EmailRecord
python3 tools/ValidateContracts.py classified.json ClassificationResult
python3 tools/ValidateContracts.py extracted.json  DocumentExtract
python3 tools/ValidateContracts.py compared.json   ComparisonResult
python3 tools/ValidateContracts.py entry.json      SubmissionEntry
```

With no arguments it checks every fixture instead:

```bash
python3 tools/ValidateContracts.py
```

A failure names the field and what was wrong:

```
FAIL - 3 violation(s):
  SubmissionEntry.status: 'MISMATCHED' not one of ['OK', 'MISMATCH', 'NEEDS_REVIEW']
  SubmissionEntry.has_defect: expected boolean, got str
  SubmissionEntry.defect_fields[1]: 'vessel' not one of [...]
```

Exit code is 0 on pass and 1 on failure, so it drops into CI or a pre-commit
hook. Stdlib only — no `pip install`, so every stage can run it.

Validating a whole submission before you POST it:

```python
import json
from tools.ValidateContracts import load_contract, validate

schema, errors = load_contract("SubmissionEntry"), []
for email_id, entry in json.load(open("submission.json")).items():
    validate(entry, schema, email_id, errors)
print(errors or "all 520 entries valid")
```

## Documents

- `contracts/0N-*.schema.json` — the five contracts, numbered in pipeline
  order and machine-checkable
- [`docs/00-contracts.md`](docs/00-contracts.md) — what each one means and why

## The seven compared fields

`shipper` · `consignee` · `notify_party` · `port_of_loading` ·
`port_of_discharge` · `container_count` · `gross_weight_kg`

The SI is the reference; the BL is checked against it. Labels differ between
documents (`Port of Loading` vs `Load Port`), so align by meaning.
