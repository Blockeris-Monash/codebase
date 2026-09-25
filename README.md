# Shipping Document Verification — Averis x Monash Hackathon 2026

Reads a shipping inbox, classifies every email, and for document-comparison
requests checks a draft Bill of Lading against its Shipping Instruction.

**Contents** — [Start here](#start-here) · [Why it matters](#why-it-matters) ·
[How it works](#how-it-works) · [The dataset](#the-dataset-is-in-the-repo) ·
[Where the code lives](#where-the-code-lives) · [Evidence](#evidence) ·
[The five contracts](#the-five-contracts) · [Who built what](#who-built-what) ·
[Roadmap](#roadmap) · [Working on this](#working-on-this) ·
[Documents](#documents) ·
[The seven fields](#the-seven-compared-fields)

## Start here

Everything below is the fastest path from "never seen this" to "it works".

### 1 · Nothing to install

| | |
|---|---|
| **Review app** | <https://shiphappens-iota.vercel.app/> |
| **Demo video** | <https://drive.google.com/file/d/1Q_G2_Z5LWUpWRgUgYhbz7QX10cK3SfSD/view> |
| **API** | <https://blockeris-backend.onrender.com/docs> |

The app is a static page carrying its own results — all 520 emails, every
comparison already run — so it opens with no backend, no key and no network.
Only **My mailbox** (after Sign in with Google) calls the API, which sits on a
free host and can take about 100 seconds to wake. The demo data needs nothing
else. A private window gives the cleanest first look:
the page remembers your language, panel width and which emails you marked as
checked. Use an ordinary window to try the phone home screen icon.

![The review screen with a mismatch open: 46 mismatches in the inbox, and for
the open email six of the seven fields agree while gross weight differs — 40,326
KG on the shipping instruction against 41,326 KG on the draft bill of lading —
with both source documents shown underneath.](docs/img/review-mismatch.png)

One email, decided. Six fields agree, gross weight does not: 40,326 KG on the
shipping instruction against 41,326 KG on the draft bill of lading. The field is
named, and both source documents sit underneath so a person can confirm it in
seconds rather than reading two PDFs.

#### On a phone

The review app installs to the home screen and opens without browser chrome. It
carries its own results, so once installed it works with no signal at all.

**Android — Chrome.** Open <https://shiphappens-iota.vercel.app/>. Chrome
usually offers **Install** on its own; if it does not, use **⋮ → Add to Home
screen → Install**.

**iPhone or iPad — Safari.** Open the same link in **Safari**, then
**Share → Add to Home Screen**. iOS never prompts by itself and offers this only
from Safari, so a link opened inside another app's browser will not show it.

Two things that look like failures and are not. Chrome hides **Install** when
the app is *already installed* — uninstall the old copy first, and clear the
site data with **⋮ → Settings → Site settings → Clear & reset**, which also
removes the old cached copy. And a private or incognito window never offers to
install, so use an ordinary tab for this even though a private one is the better
first look at the page.

**An installed copy can be out of date, and it will not say so.** The service
worker fetches from the network first and only falls back to its cache, but an
installed app that is resumed rather than relaunched never navigates, so it
never asks. If what you see does not match the screenshot above — no shipment
reference under the subject line, no **Draft BL requests** folder — force-close
the app and reopen it. If it still differs, uninstall and clear the site data as
above. The browser at
<https://shiphappens-iota.vercel.app/> is always current; only an installed copy
can lag.

On Android the icon is baked into the wrapper Chrome generates at install time,
so it does not change in place either — the same uninstall-and-reinstall is what
picks up a new one. If Android warns that the app was *"built for an older
version of Android"*, that wrapper is Chrome's, not ours: this repository ships
no APK, and its `targetSdkVersion` is set by Google's minting service rather
than by anything in `frontend/manifest.json`.

### 2 · Get the code

Either **Download ZIP** from the green **Code** button on
<https://github.com/Blockeris-Monash/codebase>, unzip it and open the folder —
nothing in the project needs git — or:

```bash
git clone https://github.com/Blockeris-Monash/codebase.git
cd codebase
```

### 3 · Set it up

Python 3.12, plus `python3-venv` on Debian or Ubuntu. No database, no API key.

**macOS and Linux**

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m pytest -q          # 932 passed, 80 skipped (skips need a model key)
```

**Windows (PowerShell)**

```powershell
py -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m pytest -q          # 932 passed, 80 skipped (skips need a model key)
```

If the tests print 932 passed, you are done — that is the whole system checked
offline, with no key and no network. The 80 skips are the tests that reach a
model over the network; they stay skipped unless you ask for them by name.

The suite prints its own grouped report rather than a wall of dots, so the run
says what it proved:

| | |
|---|---|
| **Formats** | txt, Word, Excel and PDF parse; 242 of 250 read; the other 8 escalate |
| **EDI 304** | a different format reaching the same seven fields, delimiters read from the ISA rather than assumed, pounds converted, net weight not counted as gross |
| **Label alignment** | each shape of variation, CJK stripped before lookup, the `NET WEIGHT` decoy not claimed |
| **Comparison rules** | the locode decoy, counts, weights, suffixes; `N/A`, `TBA` and `____MT` have no value |
| **Ordering** | a blank is checked before a mismatch, so formatting is never a discrepancy |
| **Escalation wording** | the blank token is quoted rather than summarised, the wrong document names what it declares itself, a pasted address is truncated |
| **Shipment reference** | both reference shapes and neither, and that `INTERNATIONAL` is not one |
| **Classification** | the body decides, all five categories, and the evidence is true of the email |
| **Failure modes** | a missing file, an unknown format, a corrupt zip and a near-empty document all escalate; 250 files, zero exceptions |
| **Cross-check** | two independent comparators reaching the same verdict on 126 emails |
| **Contracts** | every fixture against its schema, plus a regression guard on each |
| **End to end** | eight emails, eight outcomes, and a person gets the reason |

That is a selection; the run prints all seventeen areas.

Five further tests reach a model over the network and are **skipped unless you
ask for them by name** — `SHIP_HAPPENS_LIVE=1` plus the matching key. A key on
its own is not enough, deliberately: a Gemini or Qwen key left in the
environment from another project used to unskip them, fire live calls and fail,
which says nothing about this repository. `QWEN_BASE_URL` also defaults to a
proxy only our team can reach, so someone else's key would fail against
infrastructure they have no access to. They are our liveness check, not
evidence for a reader.

### 4 · Run it

Three things, each in the activated environment. **Keep it activated**: `python`
is this project's interpreter on every platform, so every block on this page is
the same whichever machine you are on.

**The review app** — the screen in the picture above, all 520 emails:

```bash
cd frontend && python -m http.server 8099
```

Open <http://localhost:8099>. Static, so no backend and no key.

**One email through all five stages**, printed as it goes:

```bash
python -m cli.demo_pipeline email_004
```

**The API**:

```bash
python -m uvicorn backend.app:app --port 8010
```

Open <http://localhost:8010/docs>. `GET /health` and
`POST /extract-clean-compare` answer with no key, from the saved extracts in
`results/extracts/`. Ports are suggestions; anything free will do.

### If you want the live model path

`POST /classify`, `POST /process-email`, `POST /translate` and
`POST /extract-clean-compare?live=true` call Qwen, so they need `QWEN_API_KEY`
(and `QWEN_BASE_URL` for the team proxy). Copy `.env.example` to `.env` and fill
it in. `GOOGLE_API_KEY` is optional and enables only the Gemini backup
extractor, which stands behind Qwen when it stalls.

Without activating the environment, anything importing the backend fails with
`No module named 'dotenv'` — `cli.evidence`, `cli.mutation_check`,
`cli.make_results`, `cli.latency`. The rest are stdlib-only and run on any
Python 3.12.

`/extract-clean-compare` takes label/value pairs, not a file: `email_id`,
`si_pairs`, `bl_pairs`, `si_title`, `bl_title` and the two parse statuses.
`GET /mailbox` and `POST /reply` are the live mailbox: they read the signed-in
person's own Gmail and send a reply in the original thread, and both need a
Google token sent by the browser, never a key in the environment.

`cli.demo_pipeline` above builds that body for you. `/translate` renders an
email into English, Malay or Chinese; it has no caller in the review app, whose
language switch uses a built-in table in `frontend/i18n.js`, so it is an
endpoint rather than a feature of the page.

## Why it matters

A draft BL that contradicts its shipping instruction is not a typo. A
documentary credit is paid against documents rather than goods, so a discrepant
presentation can be refused by the bank under UCP 600 and payment stalls until
it is corrected. Averis's own published service list includes *"handle and
resolve LC discrepancy"*, and transport documents are the largest single source
of those discrepancies. Today someone opens both files and compares seven
fields by hand, email by email. Sourcing, and one honest limit — nothing in the
dataset says which shipments are under a credit — is in
[`docs/05-company-profile.md`](docs/05-company-profile.md).

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

### What is live, and what is a prototype

Worth saying plainly, because it changes how to read everything below.

**The AI ran, and its output is committed.** Qwen classified all 520 emails and
extracted the seven fields from all 250 attachments. Those results are in
`results/classifications/` and `results/extracts/`, and they are what the review
app shows. Every category, every field and every verdict you see began as a
model reading a document.

**The AI does not re-run when you open it.** This is a prototype: you are
looking at saved model output, not a live call, and we are not going to ask a
judge for an API key to prove otherwise. Everything *downstream* of the model
does run live on your machine — the readers parse all 250 attachments, and the
deterministic comparator recomputes every verdict from the extracts. That is the
half that decides outcomes, and it is the half you can check.

**You can verify the model's work without a model.** `python -m cli.evidence`
compares the saved AI extraction against an independent rules reader that uses
no AI at all: **1,690 of 1,694 fields agree, 0 conflicting values**. Two
independent readers of the same 250 files reaching the same answers is the
strongest thing we can offer offline, and it needs no key, no network and no
trust in us.

What you cannot check without a key is whether the model would produce those
same extracts again today. We think that is the right trade for a prototype, and
we would rather state it than let a reproducible score imply more than it does.

An escalation names the cause, not the category. Not *"missing value in
gross_weight_kg"* but **`Missing value: gross_weight_kg reads "TBA" on the
SI`**; not *"could not be confirmed as SI and BL"* but **`the file sent as the
BL declares itself "PACKING LIST"`**. The difference is what a reviewer does
next: `TBA` means a value is coming and someone should be chased, `_______`
means a form went out unfilled and the document goes back.

Each email also carries the shipment it is about — an order reference like
`5ALT-01226` or a carrier booking like `OOLU9284044566`, shown on the row and
accepted by the search box. 394 of the 520 carry one. That answers a different
question from triage: *Commercial is asking about this shipment, what happened
to it?*

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
          i18n.js                             English, Malay, Chinese
          manifest.json  sw.js  vercel.json   home screen icon on a phone
          icon-192.png  icon-512.png  apple-touch-icon.png  favicon-32.png
```

Run a CLI as a module so imports resolve from the repo root:

```bash
python -m cli.demo_read                 # what each reader does to each format
python -m cli.demo_pipeline email_004   # one email through all five stages
```

## Evidence

One command rebuilds every validation number from files in this repo:

```bash
# in the activated environment — these import the backend
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

## Roadmap

What we would build next, in order. None of it is in this version.

**1. Act on the 91 we cannot compare.** Of the 220 emails routed to comparison,
129 arrive with both documents and **91 are waiting on a draft Bill of Lading
that has not been sent yet**. We already file those on their own rather than as
review cases; the next step is to do something with them. A chase list: who owes
which draft BL, against which shipment reference — 80 of the 91 already carry
that reference, across 20 senders — ordered by how long it
has been outstanding.

That is a larger share of the work than the comparison itself, and it is not
just a backlog. UCP 600 article 14(c) requires a presentation including an
original transport document to be made no later than 21 calendar days after the
date of shipment, and never after the credit expires. A draft BL that has not
arrived is a clock running towards a refusal that no field comparison can catch,
because there is no document to compare. To count that clock we need the date of
shipment, which this dataset does not carry — a connected mailbox would supply
it. Until then the list can be ordered by age in the inbox, which is the useful
half.

**2. Read scanned documents live.** The three scanned pairs in the demo (#512–514)
show what a vision model read, beside the page itself, and still go to a person:
a value read from an image never decides a verdict. A scan that arrives by Gmail
or upload goes to a person with the reason and no reading yet. Reading those
live, with a low-confidence read landing on `missing_value` rather than a forced
verdict, is next.

**3. More mailboxes.** Gmail is connected and replies send from it. Outlook and
IMAP next, several at once. A connected mailbox also supplies the date of
shipment that makes the item 1 deadline countable.

*Finding a shipment by its reference was item 3 here and is now built; see
**How it works** above.*

**Hardening before real customer mail.** Listed with owners in #147, section B:
masking and a timeout on the drafted reply, a content security policy, clearing
a person's data from the browser on sign-out, a service worker that never caches
an error, state that survives a restart, a migration runner, and the pipeline
gaps the edge cases found (a name wrapped onto a second line, a revised BL in the
same email, decimal-comma weights).

**Later — reliability and intake.** A confidence score on the extraction, retried
before escalating. More intake channels: the X12 304 reader already exists, and
EDIFACT `IFTMIN` would be a second dialect in the same module rather than new
logic, with carrier portals and the DCSA shipping-instruction API after that —
see [`docs/03-edi-notes.md`](docs/03-edi-notes.md). A paid model tier for steady
speed without daily limits. PDF and Excel export of a review.

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
- [`docs/06-disagreement-log.md`](docs/06-disagreement-log.md) — the one place our
  output differs from the organisers' reference, and why we did not conform
- `results/evidence.md` — every validation number, rebuilt by
  `python -m cli.evidence`

## The seven compared fields

`shipper` · `consignee` · `notify_party` · `port_of_loading` ·
`port_of_discharge` · `container_count` · `gross_weight_kg`

The SI is the reference; the BL is checked against it. Labels differ between
documents (`Port of Loading` vs `Load Port`), so align by meaning.
