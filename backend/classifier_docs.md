# Classifier Documentation

# Owners/ person of contact : Hanif , Jia Jun

## What's Working

The classifier successfully identifies standard cases for the following five categories:

* `BL_COMPARISON`
* `INVOICE_QUERY`
* `SI_REQUEST`
* `GENERAL`
* `SPAM`

## Known Issues

**False Positive on `BL_COMPARISON`:** The LLM currently misclassifies emails *requesting* a draft BL as a request to *compare* a draft BL.

* **Example (`email_080`):** The model fails and categorizes this as `BL_COMPARISON`, even though the body explicitly asks to "send the draft BL" and there are no attachments present.

```json
{
  "email_id": "email_080",
  "from": "sokyong_ooi@aprilasia.com",
  "subject": "RE TO CONFIRM DOCS  5APH-59657  APAPA_NIGERIA  TOAN LUC PAPER JOINT STOCK COMPANY _ EGLV647154379937",
  "body": "Dear Deswita,\n\nPlease assist to send the draft BL for 070500212406 for checking asap.\n\nThank you.\n\nBest Regards,\nTeo Ei Leen\nShipping Documentation\nDID : +971 04 4938237\nAPRIL Fine Paper Trading (Middle East) Fze\n#813, 4 EA, Dubai Airport Free Zone\nP.O. Box : 293775, Dubai, United Arab Emirates\nWebsite : www.aprilasia.com | www.paperone.com",
  "attachments": []
}

```

## Proposed Fixes (Pending Team Discussion)

To resolve the `BL_COMPARISON` ambiguity, we have a few options to discuss:

* **Attachment Count Heuristic (Rule-based):** Check the number of attachments before calling the LLM. If `attachments: []`, immediately route to `SI_REQUEST` or `GENERAL`, bypassing the LLM entirely for `BL_COMPARISON`.
* **Attachment Content Scanning:** Pass the attachment names or file contents into the LLM context so it knows whether documents actually exist to be compared.
* **Tradeoff to discuss:** Scanning attachments or passing them to the LLM increases token usage and latency.

## How to Run

Navigate to the backend directory and start the server:

```bash
cd backend
uvicorn classifier:app --reload

```