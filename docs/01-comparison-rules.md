# Comparison rules — decision log

The organisers do not define where a real mismatch ends and a formatting
difference begins. This file is that decision plus the evidence behind it.

Every claim below was measured against `inbox/` and `attachments/` only. The
answer key was never opened, so "defect" means our reading of the documents.

Measured on: 94 `.txt` pairs, 7 `.xlsx/.xlsx` pairs.
Not yet validated: 8 `.xlsx/.docx` pairs, 13 `.pdf/.pdf` pairs.

## Headline finding

Among documents that are actually comparable, **every raw string difference is
a real defect**. Normalisation absorbed zero formatting-only differences on
both the text and Excel paths.

So normalisation's job here is *not* tidying strings. It is:

1. detecting absent values before they become false mismatches, and
2. reconciling the same value written differently across file formats.

The practical rule that follows: **be minimal.** Every extra cleaning step
only loses defects.

## The seven fields

| Field | Rule |
|---|---|
| shipper, consignee, notify_party | collapse whitespace, uppercase, exact compare. Name only — drop the address block |
| port_of_loading, port_of_discharge | strip a trailing `(ABCDE)` locode, drop trailing comma, uppercase, exact |
| container_count | parse the leading integer, ignore the type |
| gross_weight_kg | strip thousands separators and `KG`, compare as a number, tolerance 0.1 kg |

## Why each rule, with evidence

### Names — exact, name only

- Differences that are case or whitespace only: **0**. Exact compare raises no
  false alarms.
- Defects hidden in the address while the name matched: **0**. Dropping the
  address costs nothing.
- Comparing name+address concatenated would create **14 false mismatches**,
  because the address is present on one side only in the edge-case block.
- Suffix stripping loses a real defect. `email_145` has SI
  `APRIL FINE PAPER TRADING` against BL
  `APRIL FINE PAPER TRADING (MIDDLE EAST) FZE`. Strip `(MIDDLE EAST)` and
  `FZE` and both collapse to the same string — but these are two different
  legal entities, and on a title document the suffix *is* the identity.
- Fuzzy matching at a 0.85 threshold loses **0** defects; the highest
  similarity between any real defect pair is 0.727. It is not unsafe, it is
  simply useless here: it rescues nothing, adds a threshold we would have to
  justify, and starts losing `email_145` below 0.75. Exact compare has no dial.

Excel stores the party name and address in one cell, unlike the text files
which put them on separate lines. Split the cell, take the first segment.

### Ports — strip the locode, compare the name

This one is counter-intuitive and worth stating plainly.

**Every port defect keeps the UN/LOCODE identical and changes the city.**

```
email_013  SI: MOMBASA, KENYA (KEMBA)      BL: TUTICORIN, INDIA (KEMBA)
email_128  SI: NHAVA SHEVA, INDIA (INNSA)  BL: BUATAN, INDONESIA (INNSA)
email_426  SI: NEW YORK, US (USNYC)        BL: KLAIPEDA, LITHUANIA (USNYC)
```

The code is a decoy. Matching on it finds nothing; a rule that only flags when
codes differ would miss all 16 port defects.

- Pairs where the name matched but the code differed: **0**. Stripping the
  code hides nothing.
- The only non-locode parenthetical in real port values is `(WESTPORT)`, which
  is 8 characters and survives a `[A-Z]{5}` rule.
- Stripping earns its keep across formats: Excel carries no locode
  (`SINGAPORE`), text carries `SINGAPORE (SGSIN)`.

Known fragility: `(CHINA)`, `(INDIA)` and `(JAPAN)` are also five uppercase
letters and would be wrongly stripped. Harmless on the provided dataset; a
risk only if judges test with their own data.

### Container count — leading integer

- Pairs where the count matched but the type differed: **0**. The type never
  varies independently.
- All 13 real defects change the number and hold the type constant, e.g.
  `6 x 20'GP` against `5 x 20'GP`.

So `6 x 40'HC` versus `6 x 20'GP` never occurs and needs no ruling.

### Gross weight — numeric, 0.1 kg tolerance

- All 185 gross-weight lines use `KG`. No MT or LBS mixing anywhere.
- Real deltas run 500–2,000 kg, so the 0.1 kg the comparator allows cannot
  mask a genuine defect; it only absorbs float rounding. An earlier draft of
  this file said "exact, no tolerance", which never matched
  `comparator.py:110`. The code is the source of truth.
- Excel writes a bare `341715` where text writes `341,715 KG`. This is the one
  place normalisation demonstrably earns its keep.
- `NET WEIGHT: _______ MTS` sits adjacent in the SI as a decoy. Anchor the
  label match on `GROSS`.

## Ordering

Non-negotiable, because two of these steps produce false mismatches if run out
of order.

```
1. verify document type   (the filename lies on emails 501-505)
2. check sentinel/absent  -> NEEDS_REVIEW, stop here
3. normalise
4. compare
```

Sentinel values seen: `N/A`, `TBA`, `____MT`, `_______ MTS`, empty string.

`email_516` is the worked example: compare before checking and it reports both
a false weight mismatch and a false port mismatch on the same email. Check
first and it correctly escalates as `missing_value`.

## Parsing traps

- CJK appears inline in labels, including in plain `.txt`:
  `Gross Weight毛重(KGS)`, `Consignee (收货人)`. Strip CJK before matching a
  label, then collapse any empty `()` left behind.
- `&amp;` survives raw XML extraction from Office files. Unescape entities, or
  `BALL & DOGGETT` will mismatch against itself across formats.
- `.docx` and `.xlsx` are ZIP archives readable with stdlib `zipfile`; no
  dependency needed.

## Text-path outcome

Across the 94 text pairs: **51 OK**, **33 MISMATCH**, **10 NEEDS_REVIEW**.

## Open

1. `.docx` path unvalidated — 8 pairs.
2. `.pdf` path untested — 13 text pairs; needs `pypdf` or `pdfplumber`.
3. Locode regex is fragile on unseen port names.
4. If the non-text formats do show name formatting noise, fix it with a named
   rule — split on newline, take the first line — not a similarity score.
