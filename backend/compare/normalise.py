"""Reference normalisation — turning a raw document value into a comparable one.

R3 owns the production version and the rules behind it; this exists so the
fixtures carry realistic normalised values. The rules are evidence-backed:
see the comparison-rules decision log.
"""
from __future__ import annotations

import re
from collections import Counter

from backend.contracts import ComparisonRow, VerdictType

LOCODE = re.compile(r"\s*\(([A-Z]{5})\)\s*$")
# A value that stands for "not known yet". Dotted and spelled-out forms too: "T.B.A",
# "N.A.", and "TO BE ADVISED" used to compare as real values, so a blank came out
# a mismatch rather than the missing value that outranks it (#147 A3). "TBA x 40HC" is
# as unknown as "TBA"; "TBC LOGISTICS" is a company. NONE and NIL stay values: "Notify party: NONE" on both
# documents is an agreement, not a blank. The one copy: backend/app.py imports it from here.
SENTINEL = re.compile(
    r"^\s*$"
    r"|^(?:n\.?\s*/?\s*a\.?|-+|to be (?:advised|confirmed))$"
    r"|^t\.?\s*b\.?\s*[ac]\.?(?:\s*[x×]\s*\S+)?$"
    r"|^_+\s*\w*$",
    re.I)
NAME_FIELDS = frozenset({"shipper", "consignee", "notify_party"})
PORT_FIELDS = frozenset({"port_of_loading", "port_of_discharge"})
# Where a name or port ends: a pipe or a line break, never a run of spaces, which cut
# "MOORIM  SP" and "MOORIM  PAPER" to the same MOORIM (tests/edge_cases, b1d).
# The one copy: backend/app.py and cli/mutation_check.py import it from here.
NAME_SPLIT = r"\s*\|\s*|\s*[\r\n]+\s*"
LEADING_INTEGER = r"(\d+)"
# A number as a weight is written, never starting inside another one: the European
# "21.577,00", "1.234.567" and "21 577,5", then "40,326", "21 577" and "40,326.5".
# The one copy: backend/app.py imports it from here.
WEIGHT_NUMBER = (r"(?<![\d.,])(?:\d{1,3}(?:\.\d{3})+,\d+|\d{1,3}(?:\.\d{3}){2,}|\d{1,3}(?: \d{3})+,\d+"
                 r"|\d{1,3}(?:[ ,]\d{3})+(?:\.\d+)?|\d+(?:[.,]\d+)?)")
THOUSANDS_GROUP_DIGITS = 3


def normalise_name(value: str) -> str:
    """Name only — Excel stores name and address in one cell."""
    return re.sub(r"\s+", " ", re.split(NAME_SPLIT, value)[0]).upper().strip(" ,")


def normalise_port(value: str) -> str:
    """Strip the UN/LOCODE. It is identical on both sides of every planted
    port defect, so it is a decoy, never the discriminator.

    The first segment only: a port read from a PDF form can pick up the line
    beneath it, which is the vessel.
    """
    # Upper-case first: LOCODE is an [A-Z]{5} pattern, so stripping before
    # the fold leaves a lower-case "(sgsin)" in place.
    first = re.sub(r"\s+", " ", re.split(NAME_SPLIT, value)[0]).upper()

    return LOCODE.sub("", first).rstrip(",").strip()


def normalise_count(value: str) -> str | None:
    match = re.match(LEADING_INTEGER, value)

    return match.group(1) if match else None


def parse_number(written: str) -> float:
    """A WEIGHT_NUMBER as a float. A comma is the decimal point when it comes last and
    either a dot comes before it or it is not followed by exactly three digits, so
    "21.577,00" and "21 577,5" read the European way and "40,326" as 40326. A lone
    "21.577" stays 21.577: it is ambiguous, and that is how it has always been read."""
    compact = written.replace(" ", "")
    head, comma, tail = compact.rpartition(",")
    if comma and "." not in tail and ("." in head or len(tail) != THOUSANDS_GROUP_DIGITS):
        return float(f"{head.replace('.', '').replace(',', '')}.{tail}")
    if compact.count(".") > 1:
        return float(compact.replace(".", "").replace(",", ""))

    return float(compact.replace(",", ""))


# "1 x 20GP", "2×40'HC", "5X40HC": a count, then a container size.
CONTAINER_GROUP = re.compile(r"(\d+)\s*[x×*]\s*(\d{2})(?=\s*['’]?\s*[a-z]|\b)", re.I)


def container_sizes(value: str) -> Counter[str]:
    """How many containers of each size: "1 x 20GP + 2 x 40HC" is {"20": 1, "40": 2}."""
    sizes: Counter[str] = Counter()
    for count, size in CONTAINER_GROUP.findall(value):
        sizes[size] += int(count)
    return sizes


def container_total(value: str, sizes: Counter[str]) -> str:
    if sizes:
        return str(sum(sizes.values()))
    match = re.search(r"\d+", value)
    return match.group(0) if match else value.strip().upper()


def same_container_count(si: str, bl: str) -> bool:
    """Per size when both state sizes and either states two or more, since "2 x 40HC"
    is not "1 x 20GP + 1 x 40HC"; otherwise the total, as a single number was always read.
    Sizes, not type letters: 40HC and 40HQ are the same box (#147 B3)."""
    si_sizes, bl_sizes = container_sizes(si), container_sizes(bl)
    if si_sizes and bl_sizes and max(len(si_sizes), len(bl_sizes)) > 1:
        return si_sizes == bl_sizes
    return container_total(si, si_sizes) == container_total(bl, bl_sizes)


def normalise_weight(value: str) -> str | None:
    match = re.search(WEIGHT_NUMBER, value)

    return str(parse_number(match.group(0))) if match else None


def normalise(field: str, raw: str | None) -> str | None:
    """Return the comparable form, or None when the value is absent."""
    if raw is None:
        return None
    value = re.sub(r"\s+", " ", raw).strip()
    if SENTINEL.match(value):
        return None
    if field in NAME_FIELDS:
        return normalise_name(value)
    if field in PORT_FIELDS:
        return normalise_port(value)
    if field == "container_count":
        return normalise_count(value)
    if field == "gross_weight_kg":
        return normalise_weight(value)

    return value.upper()


def verdict_for(si_norm: str | None, bl_norm: str | None) -> str:
    if si_norm is None or bl_norm is None:
        return VerdictType.Missing
    if si_norm == bl_norm:
        return VerdictType.Match

    return VerdictType.Mismatch


def compare_row(field: str, si_raw: str | None, bl_raw: str | None) -> ComparisonRow:
    si_norm, bl_norm = normalise(field, si_raw), normalise(field, bl_raw)
    verdict = verdict_for(si_norm, bl_norm)
    # The norm shows the total; the verdict needs the per-size breakdown the raw values hold.
    if field == "container_count" and verdict != VerdictType.Missing:
        verdict = VerdictType.Match if same_container_count(si_raw, bl_raw) else VerdictType.Mismatch

    return {"field": field, "si_raw": si_raw, "bl_raw": bl_raw,
            "si_norm": si_norm, "bl_norm": bl_norm, "verdict": verdict}


