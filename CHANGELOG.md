# Changelog

Notable changes to this project.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and
the versions follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **Hardened for a deployment that has to stay up while judges look at it.**
  The rules say the deployed project must be *publicly accessible and functional
  during the judging period*, which turns several known gaps from tidy-ups into
  risks.

  **Every dependency is pinned exactly.** They were all `>=`, so a release
  between a green CI run and judging could change what Render built with nothing
  here going red — CI floats too, so it would have agreed with the broken
  deploy. `supabase-js` was loaded from a CDN on `@2`, a floating major: a
  release during judging would have changed the code running in a judge's
  browser without a line changing in this repository, and sign-in failing then
  would have looked like our bug. Both now name exact versions, and the suite
  passes on a clean install of exactly those.

  **A rate limit and a request id.** The backend URL is in a public repository,
  there is no auth, and one `?live=true` press spends two Qwen calls against a
  quota the whole team shares — so anyone who found it could have exhausted the
  demo before judging without meaning any harm. Thirty requests a minute per
  caller, health checks exempt because throttling the uptime monitor would put
  Render to sleep. Every response now carries `X-Request-ID`, so a failure a
  judge sees in the browser can be tied to the log line that explains it; there
  were seventeen log calls and no way to join any of them to a request.

  **Every route declares the shape it answers with.** `/process-email` returned
  `Dict[str, Any]`, so nothing checked it and the people integrating against it
  had only the source to go on.

  **`cli/validate_contracts.py` now runs in CI.** It existed and was never
  executed, which made it documentation rather than a check.

- **The scanned attachments are read, and what cannot be trusted is marked.**
  Six of the eight attachments on the five `unreadable` emails are real scans —
  about 20 KB each, one page image, no text layer at all. A vision model now
  reads all six, seven of seven fields each, behind `SHIP_HAPPENS_VISION=1` and
  off by default so the submitted numbers stay reproducible. The readings are
  cached, so a demo never waits on a free tier.

  The other two, `email_511_BL.pdf` and `email_515_BL.pdf`, are 775 and 765
  bytes: a header and binary, no image, no font, no page. Nothing reads those,
  and they stay `unreadable` because that is the correct answer rather than a
  limitation.

  **A value read from an image is never allowed to decide anything.** Comparing
  the three readable pairs produced twelve differences across 42 fields, and
  every one was the model rather than the document: a dropped space
  (`AL GURG STATIONERYLLC`), an invented comma (`APRIL, FINE PAPER TRADING`), a
  lost full stop (`PTE LTD.` for `PTE. LTD.`) and ports that lost their country
  (`NHAVA SHEVA` for `NHAVA SHEVA, INDIA`). Reading the pages by eye confirmed
  all twelve — including one this author had missed.

  So each reading is checked against the values these documents actually use.
  `cli/make_vocabulary.py` writes `results/vocabulary.json` from the 192 text
  attachments — no model, no answer key — and six of the seven fields turn out
  to draw on a small closed set: four shippers, seven loading ports, twenty
  notify parties. Gross weight takes 104 distinct values, so it has no closed
  set and is excluded rather than pretended. A reading outside the set is
  reported as read and marked **not verified**; nothing is corrected towards a
  near neighbour, because the entity pool holds deliberately near-identical
  parties and any similarity threshold loose enough to merge a scanning
  artefact would merge two real companies with it.

  These five emails escalate exactly as they did before. What changes is what a
  reviewer is handed: not "one attachment could not be read", but the seven
  fields from both documents with the doubtful values marked — which is the
  difference between opening the file yourself and not having to.

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

- **Test count: 231 to 503 without a model key.** The 1.0.0 figure above is left
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

- **The page no longer scrolls sideways on a narrow screen.** Rendered across ten
  geometries in English and Malay, every width under 500px scrolled horizontally —
  `scrollWidth` 493 against a 360px viewport, and the same 493 at 320 and at 260,
  because the figure had nothing to do with the screen. The header was a flex row
  of brand, search, language and theme controls with no `flex-wrap`.

  With that fixed, the rest of the layout stopped being sized for one handset. The
  status tiles take as many columns as fit rather than a fixed three, which is what
  the Malay labels need — *Ditandakan selesai* is eighteen characters where
  *Checked* is seven. Two panes now appear when there is room in **both**
  directions: a folding phone open is 673x841 and was getting the one-column phone
  layout, while a phone in landscape is 800x360 and was getting the desktop one,
  where `body{overflow:hidden}` left almost nothing on screen.

  `viewport-fit=cover` was set with no `safe-area-inset` anywhere, so the installed
  iOS app drew its header under the notch — and the README tells judges to install
  it on iOS. Font sizes moved from px to rem so a reader on large text or at 200%
  zoom is respected, anything you tap clears 44px, and Windows high contrast keeps
  the card edges instead of flattening the screen into undifferentiated text.

  The CSS breakpoint and the JavaScript that depends on it had already drifted: the
  script still asked about 820px after the stylesheet moved, so searching on an
  unfolded phone cleared the selection while both panes were on screen. They now
  share one definition, with a test that fails if they diverge again.

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
