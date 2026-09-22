# EDI 304 — notes

Not in the hackathon dataset. In production a Shipping Instruction usually
arrives as an X12 EDI 304 transaction rather than a document, so the reader
exists to show the extract stage is genuinely format-independent: adding it
was one entry in `READERS` and nothing downstream changed.

Tested against a real published carrier specification — C.H. Robinson's
4010 X12 304 guide — not a sample we invented. The interchange is at
`tests/samples/Edi304Sample.edi` with its provenance in the header.

## What it looks like

```
ST*304*0001~
N1*SF*Wah Lee Flocking & PVC Packing*93*0007273614~
N1*UC*ULTCONName*93*9001~
N1*N1*NOTIFY1Name*93*1007~
R4*L*UN*CNSZX~
R4*D*UN*BEANR~
N7**TBD*********CN*HLCU***4000*******CN40~
L0*1***8384*G*96000*X*8000*PCS**K**5**W~
```

Segments end with `~`, elements split on `*`. The first element names the
segment, the second is usually a qualifier saying which of several things
this one is.

| our field | segment | qualifier |
|---|---|---|
| shipper | `N1` | `SF` ship from, then `SH`, `EX` |
| consignee | `N1` | `CN` consignee, then `UC`, `ST` |
| notify_party | `N1` | `N1`, then `NP`, `N2` |
| port_of_loading | `R4` | `L` |
| port_of_discharge | `R4` | `D` |
| container_count | `N7` | one segment per container |
| gross_weight_kg | `L0` | element 5 = `G`, element 11 = unit |

## The finding that matters

**In EDI the port IS the code. In the documents the code is a decoy.**

```
document   Port of Loading: NANTONG, CHINA (CNNTG)   compare the city,
                                                     strip the locode
EDI        R4*L*UN*CNSZX                             the code is all
                                                     there is
```

Our document rule — strip the UN/LOCODE, compare the city name — is correct
*for documents*, because every planted port defect holds the code constant
and changes the city. It is not a universal rule. Comparing an EDI SI
against a document BL would need a port comparison that can match a code
against a name, which neither side currently does.

Worth knowing rather than worth building: there is no mixed EDI/document
pair in the dataset.

## Normalisation quirks the format brings

Each observed directly in the sample, not assumed.

**Accented characters are gone.** X12's basic character set is ASCII. The
sample carries `Nrnberger Strae 2`, which is `Nürnberger Straße 2` with the
non-ASCII stripped, and `OHare International Airp` for `O'Hare`. Trading
partners can agree an extended set, but you cannot rely on it.

**Names are truncated.** `R4` cuts the port name at 24 characters:
`OHare International Airp`, `AW FABER CASTELL COSMETI`,
`Wah Lee Flocking  PVC Pa`. Comparing a truncated name against a full one
would be a false mismatch, which is another reason to compare the code.

**Delimiters cannot appear in data.** `*` and `~` are structural, so a value
containing one has to be escaped or dropped. The sample shows
`Wah Lee Flocking & PVC Packing` in `N1` surviving intact but appearing as
`Wah Lee Flocking  PVC Pa` in `R4` — the ampersand removed as well as
truncated.

**Weight carries its own unit.** `L0` element 11 is `K` for kilograms and
`L` for pounds. Element 5 is the weight qualifier, `G` for gross and `N` for
net. Reading the number without both would silently mix units and mix net
into gross.

**Air and ocean use different code systems.** `R4` element 2 is `UN` for a
five-character UN/LOCODE and `IA` for a three-character IATA airport code.
`ORD` and `CNSZX` are not the same kind of identifier.

**Several parties could be "the consignee".** A 304 carries `ST` ship to,
`UC` ultimate consignee, `SD` sold to, `EX` exporter, `SU` supplier, `SF`
ship from and `16` plant. Choosing one is a judgement call, and our order is
recorded in `PARTY_QUALIFIERS`. This is the same problem as deciding between
`Consignee` and `To the Order of` on a document — codes instead of words.

## What we deliberately did not build

Connectivity. Real EDI arrives over AS2, SFTP or a VAN, with certificates,
per-carrier trading partner agreements, 997 acknowledgements and sequence
numbers. That is months of work and almost none of it is parsing.

Qualifier coverage beyond the seven fields. The 304 has hundreds of
segments; we read the ones we compare.

## Not in this dataset — checked by segment, not by extension

The opening claim is worth being able to defend precisely. Probing the
content of all 250 attachments rather than their file names:

| probe | matches |
|---|---|
| X12 interchange, group or transaction header (`ISA*`, `GS*`, `ST*`) | 0 |
| EDIFACT interchange or message header (`UNB+`, `UNH+`) | 0 |

The corpus is 192 `.txt`, 28 `.pdf`, 22 `.xlsx`, 8 `.docx`. There is no EDI
in it in any dialect. Volunteer that zero before anyone finds it: said
first it reads as scope awareness, found first it reads as padding.

## Is X12 the right dialect for this client?

Probably not — and the reader survives that, as long as the claim is stated
as architecture rather than as market knowledge.

X12 is the North American standard. The shippers in this dataset are
`APRIL Far East (M) Sdn Bhd` and `APRIL Fine Paper Trading (Middle East)
FZE`, loading in Asia and the Middle East and discharging in Korea,
Australia and Peru. On those lanes an instruction is more likely to reach
the carrier as UN/EDIFACT, through a carrier portal, or over a carrier API.

So the defensible sentence is *"a 304 is the transaction an ocean carrier
takes a shipping instruction on, and reading it shows the extract stage is
format-independent"*. The sentence to avoid is *"this is what Averis
receives"* — we have not checked what Averis receives, and the answer is not
in the dataset. Averis sits on the shipper's side of the exchange anyway;
the party that sets the message format is the carrier.

## The other intake channels

Background for the roadmap and for questions, **not checked against a
specification the way the 304 work above was.** Verify before any of it goes
on a slide.

**UN/EDIFACT `IFTMIN`** — the instruction message, EDIFACT's equivalent of a
304, and the standard outside North America. Same shape of problem:
segments, separators, qualifiers. It would be a second dialect inside
`backend/read/edi.py` with its own qualifier table, and nothing downstream
would change. This is the one to build first, if any.

**Carrier portals — INTTRA, now part of E2open.** The shipper submits one
instruction and the portal fans it out to several carriers. Intake here is
not a parsing problem: it is an account, a connection, and whatever export
the portal offers.

**DCSA APIs.** The Digital Container Shipping Association, set up by the
major container carriers, publishes standard APIs covering shipping
instructions and bills of lading. The direction of travel rather than
today's reality — and the easiest of the three to consume, because it is
JSON against a published schema.

Only the first of those three is more parsing. The other two replace the
reader with an integration, which is the same "months of work, almost none
of it parsing" point as AS2 and VANs above.

### Wording for the roadmap slide

> More intake channels. X12 304 reads today. Next: EDIFACT IFTMIN, the
> standard outside North America; carrier portals such as INTTRA/E2open;
> and the DCSA shipping-instruction API.

## Sources

- C.H. Robinson, 4010 X12 304 carrier specification — the sample and the
  segment usage
- X12 basic and extended character sets — Microsoft BizTalk documentation
- EDI 304 transaction set reference — Stedi, 1EDISource
