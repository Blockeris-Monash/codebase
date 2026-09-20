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

## Sources

- C.H. Robinson, 4010 X12 304 carrier specification — the sample and the
  segment usage
- X12 basic and extended character sets — Microsoft BizTalk documentation
- EDI 304 transaction set reference — Stedi, 1EDISource
