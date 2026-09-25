# Changelog

Notable changes to this project.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and
the versions follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

Entries marked *(audit)* are from #147. None of them changes a result on the
provided dataset: rules-first agrees 124 of 124, the mutation check catches 630
of 630, and `results.js` rebuilds with every category, status, reason, defect
field and row verdict unchanged (the section B reader fixes add continuation
lines to the raw `pairs` it displays, and nothing else). Each fix has tests that
fail without it. Section B's specs are in `docs/issues/02-audit-after-judging.md`.

### Added

- **A live email's reply is drafted only when the person asks** (#152). Checking
  My mailbox used to draft a paid reply for every general and invoice email,
  newsletters and bank notices included, and again after every restart. Those
  emails now show **Draft a reply**, which calls `POST /draft-reply` once per
  email and keeps the result. `/process-email` still drafts for API callers.
- **A colour-blind friendly switch in Settings** (#154). Action required turns
  magenta and Verified blue instead of red and green; Needs review keeps its
  amber. Works in light and dark mode, is saved on the device, and is applied
  before the first paint.
- **The demo's invoice and general emails carry a sample reply** (#151), written
  in advance and filled in from each email, labelled everywhere as a sample
  rather than the product's own draft. The demo still calls no model.
- *(audit)* **The scanned page, beside what the model read from it.** "What the scan says"
  marked doubtful values *not verified* with nothing to check them against. The
  SI and BL pages of #512–514 now sit under the reading: greyscale, cropped to
  the printed part, about 20 KB each, loaded only when the email is opened.
  `cli/make_scans.py` writes them.
- **A reviewer can confirm, dismiss or fix any field the check flagged.** Each
  differing or blank row has a Review button. *Confirm difference* agrees with
  the check. *Not a real difference* counts the field as a match. *Fix the
  reading* is for when the AI misread one document: the reviewer types what it
  says, and the new `POST /recompare` compares that field again with the same
  cleaning and rule as the full check, with no model call (it gives the saved
  verdict on all 798 demo rows). The email's status, folder, counts and reply
  draft follow the corrected fields, and "How Ship Happens decided" still shows
  what the pipeline did.

  Corrections are kept on the device first. Signed in, each one is also written
  to `corrections`, and a dismiss or a fix (or undoing one) files a human report
  to the admin queue, with the old and new values and the status change, because
  the result on screen no longer matches what the pipeline decided. A plain
  confirm files none. The report is sent first and on its own, so it does not
  depend on the corrections table accepting the row. **Run
  `backend/db/migrations/0007_correction_kind.sql` in Supabase** to add the
  `kind` and `side` columns. Until then the report still arrives, but the page
  says the correction was not sent.
- *(audit)* **A drafted reply says when no company policy stood behind it.**
  `/process-email` returns `draft_grounded` and `/draft-reply` returns
  `grounded`; the page shows "No company policy matched this email. Check the
  facts before sending." under such a draft.
- **A revised draft BL is labelled against the draft before it** (#147 D1). Each
  field is *fixed*, *still wrong*, a *new mistake* or *unchanged*, shown under the
  table as "Since the last draft". The verdict is still the latest draft against
  the SI. `ComparisonResult` gains an optional `revision` block, absent unless an
  email carries two BLs.
- **A chase list for draft BLs that never arrived** (#147 D2), in the Draft BL
  requests folder: one row per sender and shipment reference, oldest first,
  closed when a readable BL with that reference arrives from that sender, with
  *Draft a reminder*. Live mail now carries the same `awaiting` flag as the demo.

### Changed

- **Replies are drafted by Gemini first, with Qwen as the backup.** Qwen takes
  19 to 38 s to draft a reply, so under the 15 s limit the other stages use it
  never finished, and every draft waited 15 s before Gemini wrote it anyway.
  Gemini now gets 20 s, then Qwen gets 60 s behind its circuit breaker. Without a
  Gemini key, Qwen drafts alone, as before. Classification and extraction still
  ask Qwen first. (#150, on top of #148, which put reply drafting behind a
  circuit breaker so a dead Qwen no longer held every draft for 60 s.)
- **An email with an SI and a BL attached is compared without asking the AI**
  (#146), and when the AI does not answer, the keyword rule files the rest
  instead of the email coming back "could not be checked". My mailbox reads the
  documents by rule first, as the saved results do.
- *(audit)* **A document is recognised by its title's wording.** `SHIPPING
  INSTRUCTIONS`, `DRAFT BILL OF LADING`, `SEA WAYBILL` and a title followed by its
  number are an SI or a BL, not the wrong document.
- *(audit)* **An email with a revised BL or an amended SI is compared against the
  latest revision**, marked in its name or title (REVISED, AMENDED, V3, "(2)"),
  else the last attached. The evidence names the file used and those set aside,
  and the review screen shows the documents that were compared.
- *(audit)* **`SAME AS CONSIGNEE` is compared as that document's consignee**, and
  `TO THE ORDER OF`, `TO ORDER OF` and `ORDER OF` are one form. `TO ORDER`
  against `TO ORDER OF` a bank is still a mismatch. Edge case b6 now expects OK
  (decided 25 Sep).
- *(audit)* **Containers are counted per size** when either document breaks the
  count down (`1x20GP + 2x40HC`); otherwise the total decides, as before.
- *(audit)* **The Draft BL PDF for an SI request is drawn in DejaVu Sans**
  (bundled, with its licence) and returned as bytes: nothing is written to the
  server's disk, and the committed generated PDF is gone.
- *(audit)* **The startup line no longer prints `vision=on`**: the live service
  never reads scans. Setting `SHIP_HAPPENS_VISION` logs a warning saying so.
- *(audit)* **My mailbox is polled only while it is on screen**, one request at a
  time, and an answer that arrives after sign-out is dropped. The poll redraws
  the page only when the mailbox changed, and a redraw keeps focus, the cursor
  and the selection where they were, so typing a reply is no longer interrupted.
- *(audit)* **Dialogs are modal to assistive technology** and keep keyboard focus
  inside until closed, then return it. White text on the orange accent is darker
  underneath (`--accent-fill`, 4.7:1) to meet WCAG AA.
- *(audit)* **Copy says "Copied" only when the browser copied**; otherwise it
  says so and selects the text.

### Fixed

- *(audit)* **A mailbox email that could not be checked can be opened.** It was stored
  with no category and the detail pane threw on it, again on every 10-second
  poll. It now shows *Could not be checked* with **Open in Gmail**. An email
  that leaves the list between polls no longer freezes the pane either.
- *(audit)* **Two different ports no longer match.** The port rule deleted every
  five-letter word as if it were a UN/LOCODE: PORT KLANG matched PORT DICKSON,
  and BUSAN against BUSAN, SOUTH KOREA was a mismatch. Only a bracketed code is
  stripped now.
- *(audit)* **The gross weight is the number written against its unit.** The live
  cleaner joined every digit, so `2 x 20GP 40,326 KG` read as 22,040,326 kg, and
  any "MT" nearby multiplied the lot by 1000. A unit in the label counts now
  too, so a bare 40,326 under *Gross Weight (LBS)* is pounds.
- *(audit)* **`TBA.`, `T.B.A`, `TO BE ADVISED`, `N.A.` and `NIL` are missing values,** not
  mismatches, so they reach a person as the blank field they are.
- *(audit)* **A model's value must appear whole, under its own label.** The check was a
  substring of the whole document, so the shipper's name passed as the
  consignee and "100" passed out of "12,100".
- *(audit)* **Render builds with the Python CI tests.** It ignored `runtime.txt` and ran
  3.14; `.python-version` pins 3.12.3.
- *(audit)* **Policy retrieval works.** `gemini-embedding-001` answered with 3072
  numbers for a `vector(768)` column, so retrieval always returned nothing.
  Ingest and retrieval now share `backend/embeddings.py`, which asks for 768.
  **Run `backend/db/migrations/0008_policies_ingest_once.sql` in Supabase, then
  `python -m tools.ingest_policies`.** Ingest is now safe to re-run: it upserts
  on a hash of each chunk and removes chunks no longer in the manual.
- *(audit)* **Pipeline gaps found by the edge cases**, all three former xfails:
  a party name wrapped onto a legal-form line (`MOORIM SP` / `CO., LTD`), a
  decimal-comma weight (`21.577,00 KG`), and the revised BL above. Also a value
  on the line beneath its label (`.txt` and PDF), a Word or Excel row holding
  two fields, and a null field, which crashed the comparator.
- *(audit)* **Failures in reply drafting are logged** with their traceback, and
  a failed policy lookup files one technical report, instead of `print()`.
- *(audit)* **The service worker caches only good responses**, gives up on the
  network after 5 s, and never answers a script with the page. `CACHE_VERSION`
  is v7.
- *(audit)* **A refused mark, reply or read is logged** instead of looking saved:
  every Supabase call in `store.js` checks the `error` supabase-js returns.

### Security

- *(audit)* **A Word or Excel file that inflates past 8 MB is refused** instead of being
  read into memory (a zip bomb, reachable with no sign-in through Upload files
  or by email), and a PDF is read to 20 pages. An upload that yields nothing no
  longer calls the model.
- *(audit)* **The rate limit keys on an address the caller cannot write.** It trusted
  the leftmost `X-Forwarded-For`, so a new value per request skipped it. It now
  uses Cloudflare's `cf-connecting-ip`. `/mailbox` gets its own budget per
  signed-in person, and made-up callers are forgotten once idle.
- *(audit)* **`/process-email` reads only dataset files, or files this server saved for
  the request.** Any absolute path, or `../`, used to be read and its fields
  sent back: another person's Gmail attachments included.
- *(audit)* **Limits on what any caller can send.** A body past 2 MB (17 MB for
  an upload of two files) is refused before it is read; a 50 MB post used to be
  parsed whole and echoed back in the 422, which now describes the problem
  without the input. A caller's `X-Request-ID` is used only if it looks like
  one. Each mailbox's checks queue on their own, so one busy account cannot
  hold up the demo mailbox. Classification masks only the part of the body the
  prompt uses, off the event loop: masking a 100k body stalled every request
  for 6 s.
- *(audit)* **An SI request's draft never fails the email** (#145 follow-up). A
  curly quote or a dash raised out of the PDF font as a 500; the reply carried
  the PDF's server path and said it was attached; the email id could write the
  PDF outside its folder. All four are fixed.
- *(audit)* **A profile's email must be the sign-in email** (migration `0007`). Setting
  it to someone else's address made that person's first sign-in fail.
- *(audit)* **Reply drafting and refining mask personal data** before any
  model or the embedding API sees it, and restore it in the draft.
- *(audit)* **A customer's email cannot plant policy in the reply prompt.** The
  retrieved policy sits in the system instruction and the email is fenced in
  its own tag, which the email cannot close.
- *(audit)* **Every Gemini call has a timeout**: reply drafting stops at 20 s and
  the scan reader at 60 s, instead of waiting as long as Google holds the socket.
- *(audit)* **The contracts' if-and-only-if rules are enforced**: in the JSON
  schemas (`allOf`), by `cli.validate_contracts`, and by the service's own
  `ComparisonResult`.
- *(audit)* **Content security policy and security headers** on the page
  (`frontend/vercel.json`, written by `python -m cli.csp`) and on every API
  answer. supabase-js loads from its pinned UMD build with an integrity hash.
  **Editing an inline script in `index.html` or `admin.html` now means running
  `python -m cli.csp`**; the tests fail until you do.
- *(audit)* **Signing out leaves nothing of the person on the browser.** Marks,
  replies, feedback and corrections are kept under their owner's id and cleared
  when someone else signs in.

## [1.1.0] — 2026-09-25

### Added

- **The service's log lines now reach somewhere a person can read them.**
  Nothing configured logging, so `logging.getLogger(__name__)` fell back to
  Python's last resort: WARNING and above, to stderr, unformatted. Every
  `log.info(...)` already written in the backend — eighteen of them, across
  classification, reading, extraction and the rate limiter — was being discarded,
  and the warnings that did survive carried no timestamp, no logger name and
  nothing tying them to a request.

  One handler now, level from `LOG_LEVEL`, and **every line carries the same
  request id the response returns in `X-Request-ID`** — so a failure a judge saw
  in a browser can be found in Render's log viewer. The id travels in a
  `ContextVar`, because the alternative is threading it through every call
  between the middleware and whatever eventually fails. One line per request with
  how long it took, at WARNING when the status is 500 or worse so it is not read
  in the same column as every healthy request. `/health` is left out: the uptime
  monitor calls it every few minutes and would bury everything else. `httpx` and
  friends are held at WARNING for the same reason — at INFO they print a
  transcript of every Gmail and model call.

  A misspelt `LOG_LEVEL` falls back to INFO rather than silencing the service,
  which is the failure the whole module exists to prevent: `getLevelName` answers
  `"Level NONSENSE"` for anything it does not recognise, and setting that as a
  level turns logging off without saying so.

- **A second opinion on how an email was sorted, when there is a reason to
  doubt it.** Sorting is the one step with no safety net behind it: a BL check
  filed as GENERAL is never compared, and nobody is told. The live service now
  checks each answer against four signals that cost nothing: the model said it
  was unsure (0.65 or 0.50), an SI and a BL are attached but it was not filed as
  a BL check, it asks for a password or login next to a link, or it reads like an
  automatic reply but was filed as a BL check. Only then is Gemini asked the same
  question, so two tries at most, and never Gemini checking Gemini when Qwen was
  down.

  The second answer wins only when it confirms the doubt that was raised, or the
  first was unsure and the second is surer; otherwise the first stands at 0.50.
  Measured on the 520 saved answers, it asks about 5 emails (1.0%), all of them
  Qwen at 0.65; none of the wording rules fires on real mail. On the edge cases it
  catches the phishing email shown to staff as a BL task (a12) and the
  out-of-office filed as one (a11). The amendment request (a9) gives it nothing
  to go on, and a test says so.

  Every second opinion is a technical report, agreed or not. Off unless asked
  for, so the batch run that made the saved results is still Qwen alone. It can
  run on its own Gemini key and model (`GEMINI_CRITIC_API_KEY`,
  `GEMINI_CRITIC_MODEL`), because limits are per project and per model.

- **The pipeline files its own reports when the AI struggles.** The reports
  queue had an Automatic tab and nothing that wrote to it. Now every step that
  calls a model (sorting an email, reading its SI, reading its BL, drafting a
  reply) files one technical report when it took more than one model call or
  never got an answer: which email, which step, each attempt's model, result
  and time, and what happened to the email in the end. A Qwen outage that
  Gemini covered used to be invisible, and an extraction with no answer looked
  exactly like a document with blank fields. Both are now on the admin's list.

  The Automatic tab lists them **most tries first**, because the step that
  struggled most is the one to read first. The count lives in the report's
  existing `context` column, so there is no migration to run.

  One report per email and step, not one per failed call: the attempts are
  collected in a `ContextVar` while the step runs, which keeps an email's SI and
  BL apart even though they are read at the same moment. Written with the
  service-role key (`SUPABASE_SERVICE_ROLE_KEY`, server only), because a
  technical report has no user and migration 0004 lets only admins read them.
  The write runs on a background thread and a failure there is logged and
  dropped, so a paused database can never slow down or break a check. Without
  the key, reports go to the log only. A test fixture removes the key from every
  test, so a developer's `.env` cannot fill the real queue with the failures
  the tests cause on purpose.

- **A reports queue, on its own page.** `frontend/admin.html` lists what
  reviewers flagged with "Report a problem", newest first, filterable by whether
  a person or the pipeline filed it, each row linking back to the email it was
  about. It is a separate page on the same deployment rather than a route in the
  reviewer app: a Supabase session is shared across one origin, so it signs in
  alongside the inbox with nothing extra to deploy or keep awake.

  **The gate is row-level security, not the page.** Anyone can open a page and
  read its source, so hiding a link protects nothing. Migration 0004 adds an
  `admins` table with deliberately no insert policy - RLS denies what no policy
  permits, so no signed-in session can grant itself the queue - and membership
  is managed in SQL. It is keyed on **email, not user id**: a `users` row only
  exists after a first sign-in, so an id would have silently excluded anyone who
  had not signed in yet. Who is in it is pasted into the SQL editor rather than
  committed, because addresses do not belong in a repository that may be made
  public.

  It also closes something that was already there. `reports` shipped with
  `using (auth.uid() is not null)`, which reads as "the team" but means any
  account that can sign in at all; sign-in is Google, and nothing in the
  database restricts which accounts. Harmless while nothing read the table, and
  exactly the wrong policy under a page that lists everyone's reports. Filing
  one stays open to any signed-in person and they can still read their own
  back; reading everybody's now requires membership. Reads on `users` widened
  the same way, so a report can carry a name instead of a raw uuid - and that
  meant splitting the single `FOR ALL` policy, because one policy cannot widen
  `select` without widening `insert`, `update` and `delete` along with it.

- **Hardened for a deployment that has to stay up while judges look at it.**
  The rules say the deployed project must be *publicly accessible and functional
  during the judging period*, which turns several known gaps from tidy-ups into
  risks.

  **Every dependency is pinned exactly**, including the two the reply drafting
  added: `langchain-text-splitters>=0.2.0` already resolved to 1.1.2, a major
  version past its own floor, so the floor never described what CI installed. They were all `>=`, so a release
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

- **Sign in with Google.** Supabase carries the session, so a mark made on the
  demo laptop is the same mark on a phone. The page still opens signed out and
  works that way; signing in is what makes the state follow the person rather
  than the browser.

- **The live mailbox: real Gmail, read and replied to in the thread.**
  `GET /mailbox` lists the newest inbox mail, last 14 days, up to 20, and puts
  each new email through the same `/process-email` as the demo set — in the
  background, two at a time, so the page never waits on a model.
  `X-Mailbox-Pending` says how many are still being checked, and a second poll
  returns the saved result rather than paying for a second call. `POST /reply`
  sends from the reviewer's own Gmail into the original thread, to exactly one
  address; a line break in an address or subject is refused, so no extra headers
  can be smuggled in.

  **The Google token is never stored on the server.** The browser sends it with
  each request and the backend uses it for that request only — nothing in the
  database, the logs or the repository. Whose mailbox is read comes from Google,
  not from the caller: an earlier `?user_id=` form would have let anyone with a
  user id ask for someone else's mail, and now answers 401. Neither requested
  permission can delete or change mail.

  Only live mail is really sent. The 520 demo emails carry real companies'
  addresses, so their Send stays a demo.

- **Replies drafted from the company guidelines.** A policy corpus is embedded
  into `policies` (migration 0003) and retrieved to shape the wording of a
  drafted reply. The retrieved text only affects wording — the comparator's
  rules still decide the verdict, and nothing retrieved is treated as an
  instruction.

- **PII masking before anything reaches a model, and the OWASP LLM top ten.**
  Presidio masks phone numbers, personal emails and bank details on the way out,
  reversibly, so a translation can be put back together afterwards. Shipper,
  consignee and notify party are deliberately preserved, because they are the
  fields being compared. Alongside it: prompt-injection delimiters, input length
  bounds, anti-hallucination validation and a CORS configuration, written up in
  `docs/OWASP_TOP_10_COMPLIANCE.md`.

- **31 edge-case emails shaped like real customer mail**, each with its expected
  result and reason **written before the first run** — reply threads, forwards,
  Malay and Chinese, signature logos, a revised draft BL, two shipments in one
  email, an amendment, an out-of-office, phishing; and on the document side,
  name and port variants, a one-letter typo, `TO ORDER`, `SAME AS CONSIGNEE`, a
  wrapped name, a lying filename, empty, encrypted and photographed files. They
  found two real defects, both fixed below. The gaps they exposed and did not
  fix are recorded as strict expected failures, each with its reason, rather
  than quietly left out.

- **A landing page, and one look across the app.** The review screen became a
  queue rather than a list to browse: it opens on Action required, sorted by
  most issues first, the main button names the next step rather than saying
  "reply", and marking done moves to the next email with six seconds of undo. A
  progress voyage shows how far through the inbox the reviewer is.

- **Plainer status words, from the mentor session.** Match became **Verified**,
  Mismatch became **Action required**, Checked became **Done**, in all three
  languages, and each row in the list carries the number of fields needing
  attention so the worst email is the one opened first.

- **A kit for the timed manual-versus-system test.** The mentor's answer to
  "what impact evidence would convince you" was to time a person checking by
  hand against the system doing it. `cli/timed_test.py build` writes a packet of
  ten pairs and `score` marks the filled-in sheet. Two things are built in
  because a judge would look for them: the sample is stratified five OK, four
  mismatch, one review, following the corpus rather than a round number, because
  ten mismatches in a row teaches the reader to expect one and ten clean pairs
  teaches them to stop looking; and the packet is written under role-only
  filenames, because `docs.SI.name` is `email_520_SI.txt` and a reader given that
  can look the answer up, which would measure typing speed. Accuracy is scored
  alongside the seconds, since "three minutes and missed two of ten" is a
  stronger sentence than any time on its own.

- **An SI and a draft BL can be checked without signing in.** A visitor had to
  have an account before the product would do anything at all, which is a poor
  first thirty seconds for a judge with a laptop. Uploading a pair now runs the
  full comparison and shows the verdict; signing in is asked for only when
  something needs to be saved against a person.

- **The demo data is an account, not a switch beside the search box.** It sat in
  the toolbar as a toggle, which read as a filter over the mailbox rather than a
  different source of mail. It now lives in the account menu next to the signed-in
  mailbox, so the two read as what they are: two places email comes from.

- **Every email says what the sender actually wants, in a title a person can
  read.** The list showed the subject line as the sender wrote it, which on this
  corpus means `AFRT - KOPER_SLOVENIA - YM(YMJAI630397524) - 5ALT-33803 -
  5250073968 - INTERNATIONAL FOREST PRODUCTS LLC - OA`. It now reads **Draft BL
  requested: INTERNATIONAL FOREST PRODUCTS LLC · Koper, Slovenia**. Underneath
  are twelve intents sitting inside the four existing categories — check a draft
  BL against its SI, a draft BL requested, attachments missing, a new shipping
  instruction, GR missing, a question on charges, and so on. They are plain rules
  in `backend/intent.py`, not a model: the classifier and its saved results are
  untouched, so nothing about the score moves. Live Gmail mail gets the same
  treatment as the saved corpus.

### Changed

- **The labels are read before the model is asked.** Every document paid for a
  model call, including the hundreds whose label wording has been parsed since
  the first day. `backend/extract/rules.py` already aligned the reader's
  `(label, value)` pairs onto the seven fields deterministically — it was used in
  tests and nowhere in the serving path.

  Measured on the 250-file corpus: **237 documents give all seven fields by rule
  at about 1 ms each**, and across the **124 comparison emails the verdict is
  identical to the model's every time** — same status, same escalation reason,
  same exact defect set. Extraction for a pair drops from **~7.1 s to ~2 ms**;
  a live check is now the classification call and little else.

  Raw strings only agree on 89.7% of 1,694 fields, and that difference is the
  reason to look at verdicts rather than text: the model returns `ACME LTD` where
  the reader returns `ACME LTD | 80 RAFFLES PLACE...`, and `normalise.py` strips
  at the pipe. Same verdict, different string.

  **It is deliberately all-or-nothing.** A partial answer is worse than none: the
  comparator reads a missing field as something a person must look at, so six of
  seven fields would turn "not read yet" into "this document does not state a
  consignee". Anything short of all seven falls through to the model, as does any
  document that did not open. The cache still wins over both, so the submitted
  numbers are untouched — `cli.evidence` prints exactly what it did before, 630
  of 630 defects caught and 1,690 of 1,694 fields agreeing.

  **`python -m cli.rules_first_check` proves both halves on demand.** Without a
  key it runs both extractors through the same comparator over every comparison
  email and reports where the verdict differs — the check that matters, since a
  faster answer that disagrees is a regression with a stopwatch attached. With
  `--timed` it runs one real email twice against an empty cache, once forced
  through the model and once not: **8.8 s against 1.3 s, same MISMATCH, same two
  defect fields**.

  The model has not been demoted; it has been pointed at the job it was brought
  in for. A label table cannot read wording it has never seen, and that is
  precisely when the model now runs. `SHIP_HAPPENS_RULES_FIRST=0` turns the whole
  thing off in one environment variable, read per call so it takes a restart
  rather than a redeploy.

- **A signed-in account sees only its own mail, and "Check again with AI" is
  gone.** Signing in used to leave the demo data on screen with a Demo/My
  mailbox switch beside it, so it was never obvious whose mail was being looked
  at. Signing in now goes straight to the live mailbox and the switch is hidden;
  signed-out visitors get the demo exactly as before, and signing out returns to
  it. The button went with it because it had stopped meaning anything: it only
  re-ran a saved demo result, and My mailbox already puts every new email
  through the live pipeline. Its state, spinner, progress bar and glow went too,
  along with seven strings that no longer had anywhere to appear.

- **Test count: 231 to 650 without a model key.** The 1.0.0 figure above is left
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

- **Classification is bounded by the clock, not by a count of tries.** It was four
  tries with 1+2+4 seconds of backoff and a 120-second timeout on each, which is
  487 seconds in the worst case with nothing on the page saying so. The budget is
  now a single 25-second wall-clock deadline across every attempt: a try that
  cannot finish inside what is left is not started, and a gateway that accepts
  the connection and then hangs cannot push past it. `ClassificationFailed` also
  carries the upstream status now, so a 429 and a 503 stop arriving on screen as
  the same bare 502.

- **A dead gateway is no longer retried on every single email.** With Qwen down,
  each extraction still paid the full timeout before falling back, so a night of
  outage cost fifteen seconds an email for nothing. A circuit breaker now opens
  after three consecutive failures and, for the next sixty seconds, fails
  immediately so the fallback runs with no wait at all. It reopens half-way after
  the cooldown to test whether the gateway is back. It steps aside when there is
  no Gemini key, because skipping the only model that could answer is worse than
  waiting for it.

- **One name for the Supabase secret.** Two people added the same credential under
  two different names, so half the code read one and half the other and a correct
  `.env` could still leave a feature dark. `SUPABASE_SERVICE_ROLE_KEY` is now the
  only name anything reads. Settling it also closed a gap that let the test suite
  write to the live reports queue: the guard cleared one of the names and the
  fallback still accepted the other.

- **Every model call has a limit, and one document's extraction has a budget.**
  A call could wait 120 seconds and an extraction could chain several of them, so
  a single email could hold the pipeline for minutes with nothing on screen
  explaining the pause. Each call is now capped at 15 seconds and one document's
  extraction at 45 seconds in total, which is a bound a person waiting can live
  with rather than one the gateway chooses.

- **The pipeline stops filing the same report over and over.** With the gateway
  down, every email wrote an identical row and the queue filled in minutes — a
  queue of hundreds of identical rows is one nobody opens. The same title for the
  same email is now saved once in ten minutes, and one title at most three times;
  the next row saved carries "N more like this were held back", so the count is
  never lost, only the noise. Everything still goes to the log. Two failures that
  previously only went to the log now reach the queue too: an email the mailbox
  could not check, and a caller being rate limited — the latter with the address
  masked to `203.0.113.x`.

- **One place decides what is configured, and it says so at startup.** Credentials
  were read from the environment in whichever module needed them, under whichever
  name that module's author had picked. That is how reply drafting came to have
  no model at all on a documented setup: it read `GEMINI_API_KEY` while
  `.env.example` has always shown `GOOGLE_API_KEY`, so `client` was `None` and
  drafting was not degraded but dead, with nothing on screen saying so. Every
  credential now goes through `backend/settings.py`, a test fails if any module
  reads one directly, and the service prints which optional features are on when
  it starts, so a missing variable announces itself instead of being discovered
  during a demo.

- **The guidelines corpus is locked down in the migrations, not only by hand.**
  `policies` had row-level security switched on in the live project but not in
  `0003`, so a fresh deploy would have left 74 rows of company guidelines
  readable by anyone holding the publishable key, which is committed in
  `config.js`. A migration now enables it.

- **Reporting a problem asks for a sign-in first.** A visitor could press it, and
  the report went nowhere it could be attributed or acted on. The button now asks
  for an account, so a report in the queue always has a person behind it.

### Fixed

- **No flash of the wrong page after signing in.** Google returns with
  `#access_token=...` in the address. The page drew that unknown address as the
  inbox until Supabase cleared it, and an empty address is the landing page — so
  a sign-in visibly bounced inbox, landing page, mailbox. The return is now
  recognised before anything is drawn.

- **Three small things in the review screen.** The Help popup scrolls again, the
  Settings menu closes once a theme is picked, and What's next returns to the
  page it was opened from rather than always to the landing page.

- **Three defects in the batch extractor, all of them long-standing.** `--data`
  defaulted to `backend/data`, a path that has never existed, so the command in
  the module docstring extracted nothing for anyone who did not pass the flag.
  The filename was validated with `assert`, which `python -O` removes entirely,
  leaving a `TypeError` two lines later that names nothing. And one document
  that raised took the whole run with it: `job.result()` re-raises inside the
  `as_completed` loop, so a 250-document run over real model calls could die at
  the first bad file having already written part of its output, with no summary
  of what had been done. A failure is now recorded the way a model refusal
  already was, and a rerun retries it, because a rerun skips whatever is on disk.

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

- **A double space no longer cuts a name in half, and a different company no
  longer passes as OK.** A name ended at any run of two or more spaces, so
  `MOORIM  SP CO., LTD` and `MOORIM  PAPER CO., LTD` both reduced to `MOORIM`
  and matched each other. A name or port now ends only at a pipe or a line
  break. None of the 250 real attachments has two spaces inside a name, so
  nothing depended on the old split. The rule had been written out three times,
  in `app.py`, `normalise.py` and `cli/mutation_check.py`; the other two now
  import it, so the next fix cannot miss a copy.

- **Every shipment in an email is checked, not just the first.** With two SI and
  BL pairs attached, only the first pair was read, so a wrong weight on the
  second showed as OK. Files are now paired by name, each pair compared, and the
  most severe result shown, with every shipment named in the evidence. It
  applies only when there are two or more complete pairs; everything else takes
  the old path unchanged.

- **Drafting a reply no longer freezes the backend.** The retrieval-backed draft
  waited on the model for up to 120 seconds inside an async handler, which
  blocked every other request — mailbox polling, "Check again with AI", and
  `/health`, which is what the uptime monitor asks. It now runs in a worker
  thread like the extractor and classifier already did. The regression test asks
  `/health` while a 1.5 second draft is in flight and requires an answer within
  half a second.

- **An error message could be emailed to a customer.** When drafting failed it
  returned the sentence "An error occurred while generating the reply. Please
  try again." — and the page uses the draft as the reply body, so from the live
  mailbox Send would have sent exactly that to the customer. It now returns
  nothing, and the page offers no reply for that email.

- **Genuine mail is no longer filed as spam.** The classifier prompt had been
  written for the shipping dataset alone, where anything not shipping work
  looked like outside spam: GitHub notifications and bank statements were all
  landing in Spam. SPAM now means mail that tries to deceive or that nobody
  asked for; genuine mail that simply is not a shipping task is GENERAL, and
  when unsure it is GENERAL, because hiding a real email is worse than showing
  one piece of junk. Live mail carries one extra line noting that Gmail's own
  filter already passed it. Demo emails never carry that line, so the saved
  results do not move.

- **The test suite was calling real models on any machine with a `.env`.** The
  guard cleared `SUPABASE_SERVICE_ROLE_KEY` but not the other names the fallback
  accepted, so on a developer's laptop the suite reached live providers: 66.9
  seconds and failing where a clean run is 1.45 seconds and green. CI never saw
  it, because CI has no `.env` — which is exactly the shape of bug that survives
  a green pipeline. The guard now clears every name a credential can arrive
  under.

- **The top bar, the menus and the first mailbox load after signing in.** The
  account menu could open behind the page, the top bar lost its layout at narrow
  widths, and the mailbox showed zeros for a moment before its first load
  finished rather than saying it was loading.

- **An extraction that found nothing said nothing.** When every field came back
  missing, the email escalated with no explanation of why. It now files a
  technical report naming which of the two it was: nothing could be extracted,
  or the file could not be read at all. Those need different fixes and the queue
  could not tell them apart.

- **A report could be filed as somebody else, or as the pipeline.** The insert
  policy on `reports` checked only that a session existed, so a signed-in
  reviewer could write a row carrying another person's id, or one marked
  `technical` as though the pipeline had logged it. The policy now requires
  `user_id = auth.uid() and kind = 'human'`, which is the database refusing it
  rather than the page choosing not to ask. Reports also say whether they
  actually reached the queue instead of reporting success on a failed write, and
  each row is titled with the email it is about.

- **A sign-in that did not finish now says why.** Google refuses an account that
  is not on the OAuth consent screen's tester list, and it refuses *after* the
  account chooser, so a correctly configured sign-in and a broken one looked
  identical from outside: the page simply reappeared signed out with the reason
  sitting unread in the address bar. That cost an evening. The return URL's
  `error` and `error_description` are now read and shown — "This Google account
  is not on the tester list for this app. Ask the team to add it, then try again."

- **Three findings from the structure audit.** `reports.user_id` is a foreign key
  and had no index, so `on delete set null` scanned the whole table; a new
  migration adds one, rather than editing `0001`, which is already applied to the
  live project. `allow_origins=["*"]` together with `allow_credentials=True` is a
  pair a browser is required to reject; credentials are off, since no route here
  uses a cookie or an auth header. And the schema's departure from the house SQL
  conventions — `snake_case` and `uuid` rather than `PascalCase` and integer keys
  — is now declared as a deliberate deviation, because `auth.uid()` returns a
  `uuid` and every policy compares against it.

- **Three things about My mailbox that made it look broken while it worked.**
  It showed zeros before its first load finished rather than saying it was
  loading; a mailbox email opened in a desktop mail app instead of Gmail, where
  the thread actually is; and the landing page led with the demo inbox even for
  someone signed in, who wanted their own mail.

- **The landing scene.** The ship carries mixed cargo and documents rather than
  containers alone, documents drift on the water, the waves stay whole through
  their loop instead of tearing at the seam, the clouds drift, the night stars
  twinkle, the birds fly, and the progress boat is drawn above the line it
  travels and sits in port once every email is done.

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

[Unreleased]: https://github.com/Blockeris-Monash/codebase/compare/v1.1.0...HEAD
[1.1.0]: https://github.com/Blockeris-Monash/codebase/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/Blockeris-Monash/codebase/releases/tag/v1.0.0
