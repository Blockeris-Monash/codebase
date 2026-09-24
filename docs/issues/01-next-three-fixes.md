# Next three fixes — specs for review

Three items off the backlog, specified before any code. Read the open questions
at the end of each: those are the places where guessing wrong costs a rewrite.

Numbering follows the backlog, not the order of work.

---

# Fix 4 — say which blank, and which wrong document

## Goal

A reviewer opening an escalation sees the *specific* cause rather than its
category: `gross_weight_kg reads "TBA" on the SI` instead of `Missing value
detected in fields: gross_weight_kg`, and `the file sent as the BL declares
itself "PACKING LIST"` instead of `attached files could not be confirmed as SI
and BL`.

The use case names this axis directly: *"A score cannot fully assess whether the
system asked for human review at the right time or provided enough context."*

## Non-goals

- **Not** adding a fifth `review_reason`. Routing `TBA` differently from
  `_______` is a separate decision with a contract change behind it; this fix
  only makes the cause visible.
- **Not** changing any verdict, status or `review_reason` value. No email
  changes category, outcome or score.
- **Not** touching `contracts/04-ComparisonResult.schema.json`.
- **Not** changing the classifier or extraction.

## Approach

`evidence` is already a free-form string in contract 4, described as *"One line
naming what happened. Goes on screen next to the confirm/correct action."* That
is exactly this. **No schema change is needed or wanted** — the schema sets
`additionalProperties: false`, so a new field would cascade into the schema, the
validator, all eleven fixtures and the regression guard, for information the
existing field is meant to carry.

There are **two implementations of contract 4** and they must stay in step:

| path | file | used by |
|---|---|---|
| reference | `backend/extract/rules.py::comparison_result` | fixtures, `cli.make_fixtures` |
| production | `backend/compare/comparator.py::compare` | `backend/app.py`, `cli.make_results` |

`tests/test_comparators_agree.py` asserts they agree on verdicts and escalation
reasons, not on wording — so wording may differ, but both should improve.

The data is already in hand at the point the evidence is built. In
`comparator.py` the loop holds `si_raw` and `bl_raw` (lines 195–196) when it
decides `missing`; it discards them. For the wrong document, `detect_doc_type`
returns the document's own declared title when it is neither SI nor BL, and the
reference path already puts that in evidence — `tests/test_pipeline.py:61`
asserts `"COMMERCIAL INVOICE" in comparison["evidence"]` and passes today.
Production does not. **This fix largely brings production up to the reference
path, not into new territory.**

## Data

No contract change. No new persisted field. `evidence` strings change wording.

Consequences that must be handled in the same change, not after:

- **`fixtures/*.json` carry `evidence`.** Changing the reference path's wording
  breaks `test_fixture_still_matches_what_the_pipeline_produces`. Regenerate
  with `python -m cli.make_fixtures --out fixtures` **in the same commit**.
- **`frontend/results.js` carries `evidence`.** Regenerate with
  `python -m cli.make_results` in the same commit, or the screen shows the old
  sentence while the API shows the new one.
- `results/evidence.md` does not quote these strings. No action.

## Interface

No signature changes. `compare(email_id, si_doc, bl_doc)` and
`comparison_result(email_id, si, bl)` keep their shapes.

Evidence wording, both paths:

```
missing_value    Missing value: gross_weight_kg reads "TBA" on the SI.
                 Missing value: shipper is blank on the SI; consignee reads
                 "N/A" on the BL.
wrong_doc_type   Document type error: the file sent as the BL declares itself
                 "PACKING LIST".
unreadable       Unreadable document: the BL could not be parsed (image-only
                 PDF, no text layer).
```

A helper holds the phrasing so the two paths cannot drift:

```python
# backend/compare/evidence.py
def describe_blank(field: str, side: str, raw: str | None) -> str: ...
def describe_wrong_doc(side: str, declared: str | None) -> str: ...
```

## Error cases

| case | behaviour |
|---|---|
| raw is `None` or `""` | say `is blank`, never quote an empty string |
| raw is whitespace only | treat as blank |
| raw contains `"` or `<` | the UI escapes on render; assert it in a test |
| raw is very long (a pasted address) | truncate to 40 chars with an ellipsis |
| both sides blank for one field | name both: `blank on the SI and the BL` |
| more than 3 fields missing | name the first 3, then `and N more` |
| declared title is `None` | fall back to today's generic sentence |
| declared title is the correct type | cannot happen here by construction; if it does, fall back |
| non-ASCII in the value (the corpus has Chinese labels) | pass through unchanged; the file is UTF-8 throughout |

## Test plan

- One test per blank token — `TBA`, `TBC`, `N/A`, `???`, `_______`, `____MT`,
  empty — asserting the token appears in the evidence.
- A blank on the SI and a blank on the BL name the correct side.
- Truncation: a 200-character value does not produce a 200-character sentence.
- Quotes and angle brackets in a raw value survive escaping on render.
- `wrong_doc_type` names the declared title; the existing `email_501`
  `COMMERCIAL INVOICE` test still passes.
- All five `missing_value` and five `wrong_doc_type` edge cases (emails 501–520)
  produce a sentence naming the specific cause.
- `test_comparators_agree` still passes — verdicts unchanged.
- `cli.validate_contracts` passes with no schema edit.
- Full suite green, and `cli.evidence` output unchanged (it quotes counts, not
  evidence strings).

## Open questions

1. **Should `TBA`/`TBC` eventually route to their own `review_reason`?** They
   mean "a value is coming, chase it", which is operationally different from
   "the form was never filled". That is a contract change and a scoring risk.
   *Assumption if unanswered: no. Wording only, this round.*
2. **Should the two paths share one wording helper, or is drift acceptable?**
   *Assumption: share it. Two sentences for one fact is how they diverge.*

---

# Fix 8 — find a shipment by its reference

## Goal

Type `5ALT-01226` or `OOLU1187233351` into the search box and find the email;
see the reference on the row without opening it. Answers the client's own
service line: *support the Commercial team on any shipping documentation query
raised by the end customer*.

## Non-goals

- **Not** a tracking system, a shipment record, or a join across emails. No
  reference appears twice in this corpus (601 distinct, zero repeated).
- **Not** parsing references out of attachments — subject and body only.
- **Not** changing the folders, counts, verdicts or any existing search
  behaviour. A search that works today must return the same rows tomorrow.

## Approach

Extract in **Python**, in `cli/make_results.py`, where it is unit-testable and
where the rest of the per-email derivation already lives — not in JavaScript,
which has no test runner in this repo. `frontend/results.js` is a build
artefact, not a contract, so adding a key needs no schema change.

The UI then does three small things: show the reference on the row, add it to
the search haystack, and say that the box accepts one.

`items()` currently searches `subject + from + id`. It does **not** search the
body. Adding `ref` to the haystack makes body-only references findable without
making the whole body searchable — which would change what existing searches
match, and is a non-goal.

## Data

`frontend/results.js`, per entry, gains one optional key:

```json
{ "id": "email_495", "ref": "OOLU1187233351", ... }
```

Absent when no reference is found. Present on roughly 62 of the 91 awaiting
emails and a majority of the rest — the exact count is a test assertion, not a
guess.

## Interface

```python
# cli/make_results.py
SHIPMENT_REF = re.compile(...)          # named constant, not inline
def shipment_ref(subject: str, body: str) -> str | None:
    """The first shipment reference in the subject, else in the body."""
```

Subject is searched before body so the displayed reference matches what the
reader already sees in the list.

## Error cases

| case | behaviour |
|---|---|
| no reference anywhere | key absent; row renders as today; search unaffected |
| several references | take the first by the rule above — deterministic, never "any" |
| reference only in the body | extracted and searchable; shown on the row |
| a container number that looks like a reference | anchored to known carrier prefixes plus the `5ALT-01226` order pattern, not a loose alphanumeric run |
| lowercase in the search box | matched case-insensitively, as the existing search is |
| reference contains characters needing escaping | rendered through the existing `hl()`/`esc()` path, which is already XSS-safe |
| `results.js` rebuilt without this change | UI must not break on a missing `ref` — guard the render |

## Test plan

- `shipment_ref` on real subjects from the corpus: a carrier reference, an order
  reference, both present, neither present, body-only.
- The count of awaiting emails carrying a reference is asserted (currently 62 of
  91), so a regex regression is visible.
- Searching a known reference returns exactly the expected email.
- Every existing search still returns what it returned before — a test over a
  handful of current terms.
- `tests/test_i18n.py` covers the new label string in all three languages, which
  it will fail on until the translations are added.
- `cli.make_results` output remains byte-identical apart from the new key.

## Open questions

1. **Show the reference on every row, or only when it matches the search?** The
   email number chip today only appears when it matches.
   *Assumption: always show it. It is the thing a reviewer quotes back to
   Commercial, not a search artefact.*
2. **Should the search box placeholder change from "Search mail"?** It is a
   translated string in three languages.
   *Assumption: yes — "Search mail or shipment reference", translated.*

---

# Fix 6 — write the disagreement log

## Goal

A short document recording every place our output differs from the organisers'
reference, and why. The use case asks for exactly this: *"If your result differs
from the reference, check the source documents before changing it. If your
decision is reasonable, record the reason."*

## Non-goals

- **Not** a change to any code, verdict or score.
- **Not** a list of grievances. One class exists; if the log grows past two or
  three it has become an excuse sheet and should be reconsidered.
- **Not** a place to reproduce the answer key. See the constraint below.

## Approach

A new file following the existing `docs/` convention — lowercase, numeric
prefix, next free number — written in the same voice as
`docs/01-comparison-rules.md`: claim, evidence, and the limit of the claim.

The single disagreement, verified across all 520 emails:

> The reference marks **91 emails that carry zero attachments** as
> `BL_COMPARISON` with status `OK`. The organisers' own schema defines `OK` as
> *"compared cleanly, everything matches"*. Nothing was compared. We escalate
> them as `missing_attachment` and file them as awaiting a document.

## Data

None. No code, no output, no contract.

## Error cases

Not a program, but two ways to get it wrong:

- **Leaking the key.** `ground_truth.json` is gitignored four ways and has never
  been committed. The log may cite the category and status of the class under
  discussion and the count; it must not paste the file, quote unrelated entries,
  or list per-email values.
- **Overstating.** The claim is that the reference contradicts its own schema on
  one class. It is not that our score is understated, that the scorer is wrong,
  or that we would score higher another way.

## Test plan

No test. Instead, re-verify the claim programmatically at the moment of writing
and record the command in the document, so a reader can repeat it:

```
520 emails compared against the reference
  1 disagreement class, 91 emails: zero attachments marked OK
  0 disagreements on category, defect_fields, or any other status
```

## Open questions

1. **Publish in the repo, or keep internal?** The repository is public and the
   README already states the classifier prompt was fitted to the key.
   *Assumption: publish. The brief invites it, and half-disclosing is worse than
   either alternative.*
2. **Does this belong in `docs/` or `docs/issues/`?** It is a standing record,
   not a defect.
   *Assumption: `docs/`, as `06-`.*

---

## Sequencing

Fix 6 first — it is writing, touches no code, and cannot break anything.
Fix 8 second — Python-side and testable, one new key, no contract.
Fix 4 last — two code paths, and it forces a fixtures and `results.js`
regeneration that is easier to review on a quiet tree.

## Ownership

`backend/compare/comparator.py` is JJ's and `frontend/index.html` is Milk's.
Fix 4 touches the first, fix 8 the second. Confirm before either lands.
