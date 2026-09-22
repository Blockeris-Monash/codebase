# Shipping Document Verification — Averis x Monash Hackathon 2026

Reads a shipping inbox, classifies every email, and for document-comparison
requests checks a draft Bill of Lading against its Shipping Instruction.

A draft BL that contradicts its shipping instruction is not a typo. A
documentary credit is paid against documents rather than goods, so a discrepant
presentation can be refused by the bank under UCP 600 and payment stalls until
it is corrected. Averis's own published service list includes *"handle and
resolve LC discrepancy"*, and transport documents are the largest single source
of those discrepancies. Today someone opens both files and compares seven
fields by hand, email by email. Sourcing, and one honest limit — nothing in the
dataset says which shipments are under a credit — is in
[`docs/05-company-profile.md`](docs/05-company-profile.md).

**Contents** — [Try it live](#try-it-live) · [How it works](#how-it-works) ·
[Setup](#setup) · [The dataset](#the-dataset-is-in-the-repo) ·
[Where the code lives](#where-the-code-lives) · [Evidence](#evidence) ·
[The five contracts](#the-five-contracts) ·
[Who built what](#who-built-what) ·
[Documents](#documents) · [The seven fields](#the-seven-compared-fields)

## Try it live

- Demo video: <https://drive.google.com/file/d/1Q_G2_Z5LWUpWRgUgYhbz7QX10cK3SfSD/view>
- Review app: <https://shiphappens-iota.vercel.app/>. Static page with every
  comparison already run. On a phone you can add it to the home screen as an
  icon that opens the same page.
- Backend: <https://blockeris-backend.onrender.com/docs> — every endpoint
  listed, and runnable from the page. (`/health` returns `{"status": "ok"}`;
  the bare root is not a page and answers 404.) The **Check again with AI**
  button in the app calls this service. It runs on a free host, so the first
  request after a quiet spell can take about 100 seconds.

![The review screen with a mismatch open: 46 mismatches in the inbox, and for
the open email six of the seven fields agree while gross weight differs — 40,326
KG on the shipping instruction against 41,326 KG on the draft bill of lading —
with both source documents shown underneath.](docs/img/review-mismatch.png)

One email, decided. Six fields agree, gross weight does not: 40,326 KG on the
shipping instruction against 41,326 KG on the draft bill of lading. The field is
named, and both source documents sit underneath so a person can confirm it in
seconds rather than reading two PDFs.

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

Then, in the project folder either way.

**macOS and Linux:**

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m pytest -q          # 231 passed, 5 skipped (skips need a model key)
```

**Windows (PowerShell):**

```powershell
py -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m pytest -q          # 231 passed, 5 skipped (skips need a model key)
```

Python 3.12, plus `python3-venv` on Debian or Ubuntu. No database.

**Every command below assumes that activated environment**, where `python` is
this project's interpreter on all three platforms — so every block on this page
is the same whichever you are on. Without activating, anything that imports the
backend dies with `No module named 'dotenv'`: `cli.evidence`,
`cli.mutation_check`, `cli.make_results` and `cli.latency`. The rest —
`cli.smoke_test`, `cli.demo_read`, `cli.demo_pipeline`, `cli.make_fixtures`,
`cli.validate_contracts` — are stdlib-only and run on any Python 3.12.

The review app, the tests and the saved comparison path need no API key. Only
the live model calls do, and each is marked below.

### See the prototype

```bash
cd frontend && python -m http.server 8099
```

Open <http://localhost:8099>. All 520 emails, every comparison already run.
The page is static — it reads `frontend/results.js` — so it needs no backend,
no key and no network.

### Run the API

```bash
python -m uvicorn backend.app:app --port 8010
```

<http://localhost:8010/docs>. `GET /health` and `POST /extract-clean-compare`
answer with no key, from the saved extracts in `results/extracts/`.
`POST /classify`, `POST /process-email`, `POST /translate` and
`POST /extract-clean-compare?live=true` call Qwen, so they need `QWEN_API_KEY`
(and `QWEN_BASE_URL` if you go through the team proxy). `GOOGLE_API_KEY` is
optional and enables only the Gemini backup extractor, which stands behind Qwen
when Qwen stalls. Copy `.env.example` to `.env` and fill it in. Ports 8010 and
8099 are suggestions; anything free will do.

`/translate` renders an email and its documents into English, Malay or Chinese.
It has no caller in the review app — the language switch uses a built-in table
in `frontend/i18n.js` — so it is an endpoint, not a feature of the page.

`/extract-clean-compare` takes the label/value pairs, not a file: the body is
`email_id`, `si_pairs`, `bl_pairs`, `si_title`, `bl_title` and the two parse
statuses. For a worked end-to-end call that reads the documents and builds that
body for you:

```bash
python -m cli.demo_pipeline email_004     # one email through all five stages
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

`DATA_DIR` moves the classifier's inbox only (`backend/classify.py`) — a
folder, or the kit's server URL. The tools that read documents take `--data`
instead: `cli.demo_pipeline`, `cli.evidence`, `cli.make_fixtures` and
`cli.make_results`. The rest read `data/` directly.

## Where the code lives

Everything importable is under `backend/`, named after the pipeline stage it
serves. Anything you run by hand is under `cli/`.

```
backend/
├── contracts.py      the five contract types, one source of truth
├── app.py            FastAPI service: /health, /classify, /extract-clean-compare,
│                    /process-email, /translate
├── translate.py      the /translate endpoint's model call
├── classify.py       stage 1 - email to category
├── read/             stage 2 - file bytes to (label, value) pairs
│   ├── documents.py    txt, docx, xlsx, pdf
│   ├── edi.py          X12 304
│   └── labels.py       label spellings the readers align on
├── extract/          stage 3 - pairs to the seven fields
│   ├── rules.py        deterministic, no API calls
│   ├── ai.py           model-backed extractor
│   ├── gemini.py  qwen.py  batch.py  sample.py
│   └── fallback.py     Gemini behind Qwen when Qwen fails or stalls
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
python -m cli.demo_read                 # what each reader does to each format
python -m cli.demo_pipeline email_004   # one email through all five stages
```

## Evidence

One command rebuilds every validation number from files in this repo:

```bash
python -m cli.evidence            # writes results/evidence.md
python -m cli.mutation_check      # break one BL field at a time, check the verdict
python -m cli.latency --n 10      # time the live pipeline (needs QWEN_API_KEY)
```

`cli.evidence` compares the saved AI extraction with the rules reader,
summarises the pipeline results and the classifier, and reads the hand labels in
`results/classifier_handlabels.json`. It reads no organiser answer key: every
number it prints comes from files in this repo.

The classifier prompt itself is a different matter. It was corrected against the
organisers' key (`5e76cff`), so the classification score is fitted rather than
held out, and we say so. The mutation check, the rules-reader agreement and the
hand labels never touch the key.

## The five contracts

Five shapes pass between stages, defined as JSON Schema in `contracts/` and
explained in [`docs/00-contracts.md`](docs/00-contracts.md). A worked example
of each is in `fixtures/`. Any stage can be built and tested in isolation
against a fixture — nobody waits on the stage upstream.

The numbers below are the **contracts**, not the stages — each is the shape
handed from one stage to the next, and `contracts/0N-*.schema.json` is numbered
to match.

```
Inbox ──1── Classify ──2── Extract ──3── Compare ──4── Report
                                                 └──5── submission.json

1 EmailRecord   2 ClassificationResult   3 DocumentExtract
4 ComparisonResult   5 SubmissionEntry
```

## Who built what

| Area | Owner |
|---|---|
| Data contracts, the readers for every file format, the phone home screen icon | Elyesa Tee |
| Backend API, `/process-email`, pipeline orchestration, Render deployment | Hanif Rafli |
| Comparator engine — the Match, Mismatch and Needs review rules | Ho Jia Jun |
| Report screen wired to the live backend, hosting, merges, submission | Tan Le Han |
| AI extraction and saved results, the review interface, validation evidence | Athith Kounsana |

## Working on this

Team process — the developer checks, regenerating fixtures and validating a
stage's output against its contract — is in
[`CONTRIBUTING.md`](CONTRIBUTING.md).

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
  `python -m cli.evidence`

## The seven compared fields

`shipper` · `consignee` · `notify_party` · `port_of_loading` ·
`port_of_discharge` · `container_count` · `gross_weight_kg`

The SI is the reference; the BL is checked against it. Labels differ between
documents (`Port of Loading` vs `Load Port`), so align by meaning.
