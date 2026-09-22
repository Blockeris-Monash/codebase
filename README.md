# Shipping Document Verification — Averis x Monash Hackathon 2026

Reads a shipping inbox, classifies every email, and for document-comparison
requests checks a draft Bill of Lading against its Shipping Instruction.

## Try it live

- Review app: <https://shiphappens-iota.vercel.app/>. Static page with every
  comparison already run. On a phone you can add it to the home screen as an
  icon that opens the same page.
- Backend: <https://blockeris-backend.onrender.com/docs> — every endpoint
  listed, and runnable from the page. (`/health` returns `{"status": "ok"}`;
  the bare root is not a page and answers 404.) The **Check again with AI**
  button in the app calls this service. It runs on a free host, so the first
  request after a quiet spell can take about 100 seconds.

A private or incognito window gives a clean first look: the page remembers your
language, your panel width and which emails you marked as checked, and it
registers a service worker. Use an ordinary window if you want to try the phone
home screen icon — a private window will not offer it.

## How it works

Five stages, with a JSON contract between each one.

| | Stage | What it does |
|---|---|---|
| 1 | Classify | Qwen files each email as `BL_COMPARISON`, `SI_REQUEST`, `INVOICE_QUERY`, `GENERAL` or `SPAM` |
| 2 | Read | text, Word, Excel, PDF and X12 EDI into `(label, value)` pairs |
| 3 | Extract | Qwen pulls the seven compared fields out of those pairs |
| 4 | Compare | plain Python rules give the verdict |
| 5 | Review | the web app, where a person decides |

The model extracts and the rules decide. A value the model returns must appear
verbatim in the source document or the field is dropped, and a missing field
escalates the pair rather than passing it.

Three outcomes:

- **Match** — all seven fields agree.
- **Mismatch** — a field differs, and the report names which.
- **Needs review** — a blank value, an unreadable file, the wrong document type
  or a missing attachment. No value is inferred.

## Setup
**Download the ZIP.** On <https://github.com/Blockeris-Monash/codebase>, the
green **Code** button → **Download ZIP**. Unzip it and open the folder in your
IDE. Nothing in the project needs git.

**Or clone it.**

```bash
git clone https://github.com/Blockeris-Monash/codebase.git
cd codebase
```

Then, in the project folder either way:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

.venv/bin/python -m pytest -q          # 219 passed, 5 skipped (skips need a model key)
```

Python 3.12. No database. The review app, the tests and the saved comparison
path need no API key. Only the live model calls do, and each is marked below.
On Windows, use python or py instead of python3, and access virtual environment binaries via .\.venv\Scripts\ instead of .venv/bin/.

### See the prototype

```bash
cd frontend && ../.venv/bin/python -m http.server 8099
```

Open <http://localhost:8099>. All 520 emails, every comparison already run.
The page is static — it reads `frontend/results.js` — so it needs no backend,
no key and no network.

### Run the API

```bash
.venv/bin/python -m uvicorn backend.app:app --port 8010
```

<http://localhost:8010/docs>. `GET /health` and `POST /extract-clean-compare`
answer with no key, from the saved extracts in `results/extracts/`.
`POST /classify`, `POST /process-email` and `POST /extract-clean-compare?live=true`
call Qwen, so they need `QWEN_API_KEY` (and `QWEN_BASE_URL` if you go through
the team proxy). Copy `.env.example` to `.env` and fill it in. Ports 8010 and
8099 are suggestions; anything free will do.

`/extract-clean-compare` takes the label/value pairs, not a file: the body is
`email_id`, `si_pairs`, `bl_pairs`, `si_title`, `bl_title` and the two parse
statuses. For a worked end-to-end call that reads the documents and builds that
body for you:

```bash
python3 -m cli.demo_pipeline email_004     # one email through all five stages
```

## The dataset is in the repo

`data/` holds the 520 emails and 250 attachments. The organisers confirmed
on 19 Sep that the provided dataset may be committed to a public repo and
that judging uses that dataset only, so a judge can clone this and run it
without downloading anything.

```
codebase/
├── data/inbox/          520 email records
├── data/attachments/    250 SI and BL documents
└── data/sample_submission.json
```

The organiser Docker kit stays out, and `.gitignore` blocks it by both path
and filename: it contains the answer key.

`loader.py` at the root is the organisers' own loader, byte-for-byte
unmodified, and `data/` keeps the bundle's layout — so the dataset is the one
they shipped, reachable the documented way (`Inbox("data")`).

Point the code somewhere else with `DATA_DIR`, or `--data` on any tool.

## Where the code lives

Everything importable is under `backend/`, named after the pipeline stage it
serves. Anything you run by hand is under `cli/`.

```
backend/
├── contracts.py      the five contract types, one source of truth
├── app.py            FastAPI service: /health, /classify, /extract-clean-compare, /process-email
├── classify.py       stage 1 - email to category
├── read/             stage 2 - file bytes to (label, value) pairs
│   ├── documents.py    txt, docx, xlsx, pdf
│   ├── edi.py          X12 304
│   └── labels.py       label spellings the readers align on
├── extract/          stage 3 - pairs to the seven fields
│   ├── rules.py        deterministic, no API calls
│   ├── ai.py           model-backed extractor
│   ├── gemini.py  qwen.py  batch.py  sample.py
└── compare/          stage 4 - SI against BL
    ├── normalise.py    per-field normalisation
    └── comparator.py   the verdict

cli/      demo_read  demo_pipeline  smoke_test  validate_contracts
          make_fixtures  make_results  evidence  mutation_check  latency
frontend/ index.html  results.js  config.js   the review UI, static
          manifest.json  sw.js  icons         home screen icon on a phone
```

Run a CLI as a module so imports resolve from the repo root:

```bash
python3 -m cli.demo_read                 # what each reader does to each format
python3 -m cli.demo_pipeline email_004   # one email through all five stages
```

## Evidence

One command rebuilds every validation number from files in this repo:

```bash
python3 -m cli.evidence            # writes results/evidence.md
python3 -m cli.mutation_check      # break one BL field at a time, check the verdict
python3 -m cli.latency --n 10      # time the live pipeline (needs QWEN_API_KEY)
```

`cli.evidence` compares the saved AI extraction with the rules reader,
summarises the pipeline results and the classifier, and reads the hand labels in
`results/classifier_handlabels.json`. It reads no organiser answer key: every
number it prints comes from files in this repo.

The classifier prompt itself is a different matter. It was corrected against the
organisers' key (`5e76cff`), so the classification score is fitted rather than
held out, and we say so. The mutation check, the rules-reader agreement and the
hand labels never touch the key.

## Developer checks

```bash
# 1. dataset reachable, both ways
python3 -m cli.smoke_test
python3 -m cli.smoke_test http://localhost:8081

# 2. regenerate stage fixtures from real emails
python3 -m cli.make_fixtures --out fixtures

# 3. check everything still satisfies the contracts
python3 -m cli.validate_contracts
```

The scoring server runs on **8081**, not 8080 — 8080 is commonly taken. Start
it from the organiser kit with `docker compose up -d`.

`frontend/results.js` is a build artefact, not hand-written. It is every email
with its category, its verdict and both documents, rebuilt from `results/` by:

```bash
python3 -m cli.make_results         # -> frontend/results.js
```

If you hold the organisers' `ground_truth.json`, you can score this yourself
with their `score_cli.py`; our saved results come out at 1.0000. The repository
ships no `submission.json`, because it is a self-check rather than a
deliverable — `cli.make_fixtures` writes a `SubmissionSample.json` showing the
shape.

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
| Data contracts, the readers for every file format, the phone home screen icon | Elyesa Tee |
| Backend API, `/process-email`, pipeline orchestration, Render deployment | Hanif Rafli |
| Comparator engine — the Match, Mismatch and Needs review rules | Ho Jia Jun |
| Report screen wired to the live backend, hosting, merges, submission | Tan Le Han |
| AI extraction and saved results, the review interface, validation evidence | Athith Kounsana |

## Check your output before handing it on

Write one record to a JSON file and name the contract it should satisfy:

```bash
python3 -m cli.validate_contracts out.json ComparisonResult
```

Fixtures are numbered by email id — `01-Ok.json` through `11-SendDraftBlUnresolved.json`.

Per stage:

```bash
python3 -m cli.validate_contracts record.json     EmailRecord
python3 -m cli.validate_contracts classified.json ClassificationResult
python3 -m cli.validate_contracts extracted.json  DocumentExtract
python3 -m cli.validate_contracts compared.json   ComparisonResult
python3 -m cli.validate_contracts entry.json      SubmissionEntry
```

With no arguments it checks every fixture instead:

```bash
python3 -m cli.validate_contracts
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
from cli.validate_contracts import load_contract, validate

schema, errors = load_contract("SubmissionEntry"), []
for email_id, entry in json.load(open("submission.json")).items():
    validate(entry, schema, email_id, errors)
print(errors or "all 520 entries valid")
```

## Documents

- `contracts/0N-*.schema.json` — the five contracts, numbered in pipeline
  order and machine-checkable
- [`docs/00-contracts.md`](docs/00-contracts.md) — what each contract means and why
- [`docs/01-comparison-rules.md`](docs/01-comparison-rules.md) — the rule for
  each of the seven fields, with the evidence from the corpus behind it
- [`docs/02-hand-trace.md`](docs/02-hand-trace.md) — one email followed through
  all five stages by hand, to check the code against
- [`docs/03-edi-notes.md`](docs/03-edi-notes.md) — the X12 304 reader, what EDI
  changes about comparison, and the other intake channels
- [`docs/04-classifier.md`](docs/04-classifier.md) — the five categories and how
  the classifier decides between them
- [`docs/05-company-profile.md`](docs/05-company-profile.md) — who the client is
  and why these seven fields are the ones worth checking
- `results/evidence.md` — every validation number, rebuilt by
  `python3 -m cli.evidence`

## The seven compared fields

`shipper` · `consignee` · `notify_party` · `port_of_loading` ·
`port_of_discharge` · `container_count` · `gross_weight_kg`

The SI is the reference; the BL is checked against it. Labels differ between
documents (`Port of Loading` vs `Load Port`), so align by meaning.
