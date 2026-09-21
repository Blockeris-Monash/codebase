# Ship Happens: evidence

Every number below is computed by `python3 -m cli.evidence` from files in this repo.

## 1. Extraction: AI against an independent rules reader
- 242 documents, 1694 fields compared after normalising both sides.
- Agree: 1690 (99.8%). Conflicting values: 0. AI only: 4. Rules only: 0.
- Agreement does not prove both are right, so the hand check (see results/validation-summary.md) reads the source files.

## 2. Detection: injected defects
- 63 emails that compare as OK; one field of the BL broken at a time.
- Defects caught on exactly the changed field: 630 of 630.
- Harmless edits (case, padding, missing UN/LOCODE) that wrongly raised a flag: 0 of 378.

## 3. What the review UI shows
- 520 emails, 126 with attachments, 126 compared SI against BL.
- Match 63, Mismatch 46, Needs review 17.
- Cleared with no human action: 50.0%. Flagged for a person: 63.
- Fields that differ in the mismatches: container_count 19, port_of_discharge 13, gross_weight_kg 12, notify_party 8, consignee 7, shipper 7, port_of_loading 6.
- Reasons for review: missing_value 5, unreadable 5, missing_attachment 5, wrong_doc_type 2.
- Categories: GENERAL 143, SI_REQUEST 136, BL_COMPARISON 126, INVOICE_QUERY 75, SPAM 40.

## 4. Classifier (Qwen)
- 520 emails classified: GENERAL 143, SI_REQUEST 136, BL_COMPARISON 126, INVOICE_QUERY 75, SPAM 40.
- Confidence below 0.85 (worth a second look): 70.
- Agrees with the plain keyword fallback on 391 of 520 (75.2%); the 129 others are where the AI adds value or errs.
- Against 50 emails read and labelled by hand (not looking at the model's answer): 46 of 46 correct (100.0%). 4 left out: send-the-draft-BL emails with no attachment, which the team has not ruled on.

## 5. Tests
- 186 passed, 4 skipped, 2 warnings

## Estimate, not a measurement
- Time saved is only an estimate: multiply the number of SI vs BL checks by the minutes a person takes to compare two documents by hand. State that assumption wherever the figure is used.

