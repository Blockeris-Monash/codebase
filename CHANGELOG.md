# Changelog

Notable changes to this project.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and
the versions follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **The test suite runs on every pull request.** A green local run is not
  evidence: it passes on one machine that has a `.env`. GitHub Actions runs
  `pytest` on Python 3.11 and 3.12 for every pull request and every push to
  `main`, from a clean clone with no credentials — which is exactly the position
  a judge following the README setup steps is in.

  No API keys are configured, deliberately, and a guard step fails the job if one
  appears. Every test that reaches a model is gated behind `SHIP_HAPPENS_LIVE`, so
  a key in CI would unskip five of them and turn a unit-test run into billed calls
  against a gateway only this team can reach.

- **What a reviewer marked now survives a change of browser.** The checked marks
  and sent replies lived in `localStorage`, which is per-device: mark forty emails
  on the demo laptop and the phone shows none of them. They now mirror to Postgres
  for whoever is signed in, alongside field corrections and problem reports — six
  tables, row-level security on every one, verified through the public API that an
  anonymous caller reads nothing and writes nothing.

  `localStorage` stays authoritative and the database is a background mirror. The
  page builds its state synchronously at load, so an async read there would mean
  rewriting the whole startup path; and this app opens *"with no backend, no key
  and no network"*, so a paused free-tier database must never be able to stop a
  mark registering. Signed out, every path is a no-op and nothing changes.

- **The shipment an email is about, on the row and in the search.** Their service
  list includes *support the Commercial team on any shipping documentation query
  raised by the end customer*, which is lookup by reference rather than triage —
  a different job from the one the seven-field check does. Typing `5ALT-01226`
  or `OOLU9284044566` now finds the email, and the reference shows on the row
  without opening it. 394 of the 520 emails carry one, including 80 of the 91
  waiting on a draft BL, which is the same key the chase list on the roadmap
  would use.

  Extracted in `cli/make_results.py` rather than in the page, because Python is
  where this repository can test it. The pattern demands a run of four digits
  after the four-letter prefix: without that, `[A-Z]{4}[A-Z0-9]{6,}` also matches
  INTERNATIONAL, OUTSTANDING and INVESTMENT — thirteen English words in these
  subjects alone, every one a false reference on a reviewer's screen.

- **`docs/06-disagreement-log.md`.** The use case asks that a result differing
  from the reference be checked against the source documents and the reason
  recorded. Ours differs in exactly one place, 91 times: the reference marks 91
  emails carrying no attachments at all as a comparison with status `OK`, which
  its own schema defines as "compared cleanly, everything matches". Nothing was
  compared. We escalate them instead, and the log states what that costs us —
  escalation precision 0.180 on the diagnostic axis — rather than only what it
  buys.

### Changed

- **Test count: 231 to 285 without a model key.** The 1.0.0 figure above is left
  as it was - it was true of that release and a changelog that edits its own
  history is worth nothing.

- **An escalation now names its cause instead of its category.** `Missing value
  detected in fields: gross_weight_kg` became `Missing value: gross_weight_kg
  reads "TBA" on the SI`, and `attached files could not be confirmed as SI and
  BL` became `the file sent as the BL declares itself "PACKING LIST"`.

  The distinction is operational, not cosmetic: `TBA` means a value is coming and
  someone should be chased, `_______` means a form went out unfilled and the
  document goes back, and `N/A` means a person made a call. One bucket was three
  replies. Both facts were already in hand when the escalation was built and were
  being discarded — the raw token sits in the comparison loop, and
  `detect_doc_type` returns the document's own declared title.

  No contract change: `evidence` is already described in contract 4 as "one line
  naming what happened", which is exactly this. Phrasing lives in one module,
  `backend/compare/evidence.py`, because two stages produce contract 4 — the
  reference implementation and the production comparator — and two sentences for
  one fact is how they drift apart.

  Consequences handled in the same change rather than left to be found:
  `fixtures/` and `frontend/results.js` both carry evidence strings and are
  regenerated here, so the screen and the API cannot disagree.

### Fixed

- **`/health` answers `HEAD`, not only `GET`.** The uptime monitor checks with
  `HEAD` and was getting 405, so the dashboard showed the backend as down while it
  was up and sent false alerts. The checks still kept Render awake; only the status
  was wrong.

- **Gemini now stands behind Qwen for classification and translation, not only
  extraction.** `/process-email` classifies before it extracts, so with Qwen down
  it failed at classification and never reached the one stage that had the
  backup. Classification and translation now use the same `with_fallback` as
  extraction, on the same terms: only when a Gemini key is set, same prompt and
  schema, and a Qwen reply that is not usable JSON also hands over to Gemini.
  The batch classifier stays Qwen only, because its saved results feed the quoted
  numbers and one model must have made all of them.


## [1.0.0] — 2026-09-22

First complete version: the Averis x Monash Hackathon 2026 submission. Reads a
shipping inbox, classifies every email, and for document-comparison requests
checks a draft Bill of Lading against its Shipping Instruction.

### Added

**Pipeline** — five stages with a JSON Schema contract between each one, so any
stage can be built and tested against a saved example rather than against
whichever stage finished first.

- Stage 1, classify. Qwen files each email as `BL_COMPARISON`, `SI_REQUEST`,
  `INVOICE_QUERY`, `GENERAL` or `SPAM`, with a confidence and its evidence.
- Stage 2, read. Plain text, Word, Excel and PDF into `(label, value)` pairs,
  plus an X12 EDI 304 reader. Office formats are read with the standard
  library; only PDF takes a dependency.
- Stage 3, extract. Qwen pulls the seven compared fields. A value it returns
  must appear verbatim in the source document or the field is dropped.
- Stage 4, compare. Plain Python rules give the verdict — the model never
  decides. Per-field normalisation for names, ports, container counts and
  weights.
- Stage 5, review. A static web app where a person decides.

**Escalation.** A blank value, an unreadable file, the wrong document type or a
missing attachment becomes Needs review with the reason and the source lines.
No value is ever inferred, and a missing field outranks a mismatch so a person
sees the gap first.

**Review app.** Inbox and evidence side by side with a draggable divider, the
seven fields compared with only the differing one highlighted, both original
documents underneath, search, folders, light and dark modes, English, Malay and
Chinese, drafted replies, mark-as-checked with undo, and a home screen icon on
a phone. Static: it carries its own results and needs no backend to open.

**Service.** FastAPI with `/health`, `/classify`, `/extract-clean-compare`,
`/process-email` and `/translate`. Gemini stands behind Qwen when Qwen fails or
stalls. Keys come from the environment, never the repository.

**Deployment.** Review app on Vercel, backend on Render. Saved results load
instantly; the live path runs on demand behind a button.

**Evidence.** `python -m cli.evidence` regenerates every quoted number offline
from files in the repository, with no key and no network, and is idempotent.
At this version: 630 of 630 injected defects caught with no false alarms on 378
harmless edits; the extractor agreeing with an independent rules reader on
1,690 of 1,694 fields; 231 automated tests passing without a model key, 236
with one.

**Score.** 1.0000 on the organisers' own scorer against the saved results.
Stated with its limit: the classifier prompt was corrected against the
organisers' answer key, so the classification half is fitted rather than held
out. The mutation check and the rules-reader agreement never read that key.

### Known limits

- The live model path needs `QWEN_API_KEY`; without it the saved results still
  answer.
- 8 of 250 attachments cannot be read — 6 scanned image-only PDFs needing OCR
  and 2 corrupt PDFs. They escalate rather than returning a guess.
- Time saved is an estimate from an assumed minutes-per-check, not a
  measurement.
- The review interface has not been tested with users.

[Unreleased]: https://github.com/Blockeris-Monash/codebase/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/Blockeris-Monash/codebase/releases/tag/v1.0.0
