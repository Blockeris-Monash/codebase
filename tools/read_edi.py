#!/usr/bin/env python3
"""Read an X12 EDI 304 Shipping Instruction into the same labelled pairs.

Not in the hackathon dataset - in production an SI usually arrives as an EDI
304 transaction rather than a document, so this shows the extract stage is
genuinely format-independent: everything downstream is untouched.

An interchange is segments separated by `~`, elements within a segment by
`*`. The first element names the segment, the second is usually a qualifier
saying which of several things this one is:

    N1*SF*Wah Lee Flocking & PVC Packing    N1 = a party, SF = ship from
    R4*L*UN*CNSZX                           R4 = a port,  L  = loading
    L0*1***8384*G*96000*X*8000*PCS**K       L0 = a lading line, G = gross

Tested against a real published carrier specification, not a sample we
invented. See tests/samples/Edi304Sample.edi.
"""
from __future__ import annotations

# Defaults only. X12 declares its delimiters inside the ISA segment itself,
# so a partner using "|" and a newline is just as valid - see delimiters().
DEFAULT_SEGMENT_TERMINATOR = "~"
DEFAULT_ELEMENT_SEPARATOR = "*"
COMMENT_PREFIX = "#"
INTERCHANGE_HEADER = "ISA"
ELEMENT_SEPARATOR_INDEX = 3      # ISA is fixed-width; element 1 starts at 4
ISA_LENGTH = 105                 # ISA is fixed-width; the terminator follows it
TERMINATOR_CANDIDATES = ("~", "\n", "\r")

# X12 party qualifiers, in preference order per field. A 304 carries several
# parties and more than one could stand in for "the consignee", so the order
# here is a decision, not a lookup - the same judgement the document reader
# makes between "Consignee" and "To the Order of".
PARTY_QUALIFIERS: dict[str, tuple[str, ...]] = {
    "Shipper": ("SF", "SH", "EX"),          # ship from, shipper, exporter
    "Consignee": ("CN", "UC", "ST"),        # consignee, ultimate consignee, ship to
    "Notify Party": ("N1", "NP", "N2"),     # first notify party, then second
}
PORT_QUALIFIERS: dict[str, str] = {"L": "Port of Loading", "D": "Port of Discharge"}

PARTY_SEGMENT = "N1"
PORT_SEGMENT = "R4"
CONTAINER_SEGMENT = "N7"
LADING_SEGMENT = "L0"
GROSS_WEIGHT_QUALIFIER = "G"
KILOGRAM_UNIT = "K"
POUND_UNIT = "L"
POUNDS_PER_KILOGRAM = 2.20462

# Element positions within a segment, counting the segment name as 0.
PARTY_NAME = 2
PORT_CODE = 3
PORT_NAME = 4
LADING_WEIGHT = 4
LADING_WEIGHT_QUALIFIER = 5
LADING_WEIGHT_UNIT = 11

LabelledPairs = list[tuple[str, str]]


def delimiters(text: str) -> tuple[str, str]:
    """Read the element separator and segment terminator from the ISA.

    X12 does not fix its own punctuation. The ISA segment is a fixed-width
    header whose fourth character IS the element separator, and whose
    terminator is the character following it. Hardcoding "*" and "~" works
    until a partner sends "|", which is legal and common.
    """
    start = text.find(INTERCHANGE_HEADER)
    if start < 0 or len(text) <= start + ELEMENT_SEPARATOR_INDEX:
        return DEFAULT_ELEMENT_SEPARATOR, DEFAULT_SEGMENT_TERMINATOR

    separator = text[start + ELEMENT_SEPARATOR_INDEX]

    # The ISA is fixed-width precisely so a reader can find the terminator
    # before it knows what the terminator is.
    fixed = text[start + ISA_LENGTH:start + ISA_LENGTH + 1]
    if fixed and not fixed.isalnum() and fixed != separator:
        return separator, fixed

    # Padding is sometimes lost in transit, so fall back to the first
    # plausible terminator after the header.
    found = next((c for c in text[start:] if c in TERMINATOR_CANDIDATES), None)

    return separator, found or DEFAULT_SEGMENT_TERMINATOR


def segments(text: str) -> list[list[str]]:
    """Split an interchange into segments, each a list of elements."""
    body = "\n".join(line for line in text.split("\n")
                     if not line.strip().startswith(COMMENT_PREFIX))
    separator, terminator = delimiters(body)
    # Our sample puts one segment per line for readability. Real interchanges
    # often do not, and a newline can itself be the terminator - so only
    # collapse line breaks when they are not what separates the segments.
    if terminator != "\n":
        body = body.replace("\n", "")

    return [segment.strip().split(separator)
            for segment in body.split(terminator) if segment.strip()]


def element(segment: list[str], index: int) -> str:
    """Elements are frequently omitted, so past-the-end means empty."""
    return segment[index].strip() if index < len(segment) else ""


def parties(found: list[list[str]]) -> LabelledPairs:
    """Pick one party per field, preferring the most specific qualifier."""
    by_qualifier = {element(s, 1): element(s, PARTY_NAME) for s in found}
    pairs: LabelledPairs = []
    for label, qualifiers in PARTY_QUALIFIERS.items():
        name = next((by_qualifier[q] for q in qualifiers
                     if by_qualifier.get(q)), None)
        if name is not None:
            pairs.append((label, name))

    return pairs


def ports(found: list[list[str]]) -> LabelledPairs:
    """A port is given as a code, optionally with a truncated name beside it.

    Unlike the documents - where the UN/LOCODE is a decoy and the city name
    is authoritative - in EDI the code IS the port. The name is decoration
    and is frequently cut off, so the code is what gets compared.
    """
    pairs: LabelledPairs = []
    for segment in found:
        label = PORT_QUALIFIERS.get(element(segment, 1))
        code = element(segment, PORT_CODE)
        if label is None or not code:
            continue
        name = element(segment, PORT_NAME)
        pairs.append((label, f"{name} ({code})" if name else code))

    return pairs


def gross_weight_kg(found: list[list[str]]) -> LabelledPairs:
    """Sum the gross weight across lading lines, converting if needed."""
    total = 0.0
    for segment in found:
        if element(segment, LADING_WEIGHT_QUALIFIER) != GROSS_WEIGHT_QUALIFIER:
            continue
        weight = element(segment, LADING_WEIGHT)
        if not weight.replace(".", "").isdigit():
            continue
        unit = element(segment, LADING_WEIGHT_UNIT)
        value = float(weight)
        total += value / POUNDS_PER_KILOGRAM if unit == POUND_UNIT else value

    return [("Gross Weight (KG)", f"{total:,.0f} KG")] if total else []


def read_edi(path) -> LabelledPairs:
    """Every field we compare, as labels the synonym table already knows."""
    found = segments(path.read_text(errors="replace"))
    by_name: dict[str, list[list[str]]] = {}
    for segment in found:
        by_name.setdefault(segment[0], []).append(segment)

    pairs = parties(by_name.get(PARTY_SEGMENT, []))
    pairs += ports(by_name.get(PORT_SEGMENT, []))

    containers = by_name.get(CONTAINER_SEGMENT, [])
    if containers:
        pairs.append(("Container Count", str(len(containers))))
    pairs += gross_weight_kg(by_name.get(LADING_SEGMENT, []))

    return pairs


def edi_title(path) -> str | None:
    """A 304 declares itself in its ST segment, not in a title line."""
    transaction = next((s for s in segments(path.read_text(errors="replace"))
                        if s[0] == "ST"), None)
    if transaction is None:
        return None

    return "SHIPPING INSTRUCTION" if element(transaction, 1) == "304" else None
