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
- 520 emails, 126 with attachments, 220 routed to comparison, 129 of those with both documents present to compare.
- Match 63, Mismatch 46, Needs review 20.
- Cleared with no human action: 48.8%. Flagged for a person: 66.
- Fields that differ in the mismatches: container_count 19, port_of_discharge 13, gross_weight_kg 12, notify_party 8, consignee 7, shipper 7, port_of_loading 6.
- Reasons for review: missing_value 5, unreadable 5, missing_attachment 5, wrong_doc_type 5.
- Categories: BL_COMPARISON 220, SI_REQUEST 125, INVOICE_QUERY 75, GENERAL 60, SPAM 40.
- A further 91 emails ask for a draft BL that is not attached yet. They are routed to comparison and go to a person, but are not counted as checks above because there is nothing to compare.

## Impact
- Of 129 SI vs BL checks, 63 (48.8%) needed no human action, and 66 were flagged with the reason and the field, so a person reads only those.
- 46 emails had a real difference between the SI and the BL, 72 differing fields in total. Each is a difference a person would otherwise have to find by reading both documents.
- The 91 draft-BL requests with nothing attached are excluded from that share. They reach a person either way, so counting them as checks the pipeline failed to clear would misstate both numbers.
- Time spared (an ESTIMATE, not a measurement): at 2 minutes per manual check, about 2.1 hours; at 3 minutes per manual check, about 3.1 hours; at 5 minutes per manual check, about 5.2 hours for the 63 cleared emails. The minutes per check are an assumption, not data.

## Speed (measured, live Qwen)
- 10 emails checked live one at a time: median 24.7 s, mean 25.4 s, slowest 43.8 s per email.
- The live answer matched the saved answer on 10 of 10.

## 4. Classifier (Qwen)
- 520 emails classified: BL_COMPARISON 220, SI_REQUEST 125, INVOICE_QUERY 75, GENERAL 60, SPAM 40.
- Confidence below 0.85 (worth a second look): 5.
- Agrees with the plain keyword fallback on 385 of 520 (74.0%); the 135 others are where the AI adds value or errs.
- Against 50 emails read and labelled by hand (not looking at the model's answer): 46 of 46 correct (100.0%). 4 left out: send-the-draft-BL emails with no attachment, which the team has not ruled on.

## Estimate, not a measurement
- Time saved is only an estimate: multiply the number of SI vs BL checks by the minutes a person takes to compare two documents by hand. State that assumption wherever the figure is used.

