# The client — Averis

Why this file exists: the brief gives us 520 emails, not a customer. This is
what the customer actually does, taken from Averis's own published material,
and what it implies for the seven fields we compare. Everything here is public.

## Who they are

Averis Sdn Bhd, founded 2006, headquartered at Wisma Averis in Bangsar South,
Kuala Lumpur. A Global Business Services provider for the RGE group of
companies.

- **1,000+ staff across 8 countries** — Malaysia, Singapore, Hong Kong, China,
  India, Dubai, Brazil, Canada
- Daily operations serve **60,000+ users across 32 locations**
- Industries: palm oil, pulp and paper, dissolving and specialty pulp, viscose,
  clean and renewable energy
- Service lines: Finance & Accounting, Human Resources, IT Operations &
  Project Services, Digital Services, **Shipping Documentation**, Corporate
  Function Services, Recruitment Process Outsourcing, Change Management

They are already an automating organisation: they adopted Robotic Process
Automation in 2018–19 and describe the goal as moving staff *"toward
higher-value consulting roles"*. That is the same move this project makes for
document verification — the mechanical comparison goes to the machine, the
judgement stays with the person.

The shippers in the dataset are RGE companies: APRIL Far East (M) Sdn Bhd,
APRIL Fine Paper Trading (Middle East) FZE. This is Averis's own traffic.

## What the shipping documentation team does

From the Averis service page, verbatim:

- Documentation preparation — Invoice, Packing List, Shipping Certificate,
  finalising the Certificate of Origin with local MITI and the chamber of
  commerce, Shipment Advice, **finalising the Bill of Lading from Freight
  forwarder and Carrier**, and Export Permit Declaration in Singapore and
  Malaysia
- Tracking of Shipping Documentation and Billing Data
- **Letters of Credit (LC) Checking** — administration of LCs, validation of
  LC policies and requirements, handle and resolve LC discrepancy
- Bill submission and related procedures
- Support the Commercial team on any shipping documentation query raised by
  the end customer
- Trade Financing Negotiation

## Our five categories are their service lines

The classification categories are not an invented taxonomy. Each maps onto
work this team is published as doing:

| Category | The service it corresponds to |
|---|---|
| `BL_COMPARISON` | finalising the Bill of Lading from freight forwarder and carrier |
| `SI_REQUEST` | shipping documentation preparation |
| `INVOICE_QUERY` | tracking documentation and billing data; supporting the commercial team on customer queries |
| `GENERAL` | operational coordination around the above |
| `SPAM` | noise arriving in the same shared inbox |

## Why the SI and the BL are not symmetric

The service description draws a line we can measure. The Shipping Instruction
originates with the shipper — an RGE company, Averis's own side. The Bill of
Lading comes back *from the freight forwarder and carrier*, which is outside
their control.

That asymmetry is visible in the corpus. Counting distinct label spellings
across every attachment that parses:

| | Shipping Instruction | draft Bill of Lading |
|---|---|---|
| distinct label spellings | **34** | **62** |
| file formats | 3 — txt, xlsx, pdf | 4 — txt, xlsx, pdf, docx |
| written languages | English | English and Chinese |

`port_of_discharge` alone carries 5 spellings on the SI side and 10 on the BL
side, including `Discharge Port (卸货港)` and `Port of Discharge (POD) (卸货港)`
— a Chinese carrier annotating the form.

This is the justification for the label-alignment layer in
[`backend/read/labels.py`](../backend/read/labels.py). The variation is not
incidental; it sits on the side of the exchange the client does not author,
and it is already present in this corpus. Supporting a new carrier means
adding a spelling to a table that already holds 62, not changing logic.

## What a defect actually costs

The service list includes *"handle and resolve LC discrepancy"*, which names
the downstream consequence of the thing we check.

A documentary credit is paid against documents, not goods. If the presented
bill of lading does not match the credit's terms, the presentation is
discrepant and the bank may refuse it under UCP 600. Payment stalls until the
discrepancy is waived or corrected.

Industry figures from the ICC:

- **60–75% of documentary credit presentations are refused on first
  submission** (ICC Academy puts the range at 65–75%)
- **transport documents — the bill of lading — are the single largest source
  of discrepancies at 38%**, ahead of commercial invoices at 27%

So the seven fields checked here sit in the document class that causes more
letter-of-credit rejections than any other, for a team whose published remit
includes resolving those rejections.

One honest limit: nothing in the dataset states which shipments are under a
letter of credit. This is the consequence the client's own service catalogue
describes, not a measured property of these 520 emails.

## What this means for the design

1. **The SI is the reference and the BL is checked against it** because that
   is the direction of authority in the real process: the shipper instructs,
   the carrier transcribes, and the transcription is what can be wrong.
2. **Label alignment is configuration, not logic**, because the variation
   comes from parties the client does not control.
3. **Escalation beats guessing.** An unmapped label makes a field absent, an
   absent value outranks a defect, and the email goes to a person with the
   reason and the source lines. On an unfamiliar carrier the cost is
   throughput, not correctness.
4. **Catching a defect early is worth more than the clerk-minutes saved**,
   because the alternative cost is a discrepant presentation.

## Sources

- Averis — [company site](https://www.averis.com/),
  [Shipping Documentation service](https://www.averis.com/services/shipping-documentation),
  [Our Story](https://www.averis.com/about-us/our-story)
- ICC Academy — [avoiding common LC discrepancies](https://academy.iccwbo.org/trade-finance/article/isbp-insights-avoiding-common-lc-discrepancies/)
- Label and format counts measured over `data/attachments/` with
  `backend.read` on 21 Sep 2026.

Validation figures for the pipeline itself are deliberately not repeated here
— they live in one place so they cannot drift between documents.
