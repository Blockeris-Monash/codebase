# Changelog

Notable changes to this project.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and
the versions follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
