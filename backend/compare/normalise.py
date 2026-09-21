"""Reference normalisation — turning a raw document value into a comparable one.

R3 owns the production version and the rules behind it; this exists so the
fixtures carry realistic normalised values. The rules are evidence-backed:
see the comparison-rules decision log.
"""
from __future__ import annotations

import re

from backend.contracts import ComparisonRow, VerdictType

LOCODE = re.compile(r"\s*\(([A-Z]{5})\)\s*$")
SENTINEL = re.compile(r"^\s*$|^(n/?a|tba|tbc|-+)$|^_+\s*\w*$", re.I)
NAME_FIELDS = frozenset({"shipper", "consignee", "notify_party"})
PORT_FIELDS = frozenset({"port_of_loading", "port_of_discharge"})
NAME_SPLIT = r"\s*\|\s*|\s{2,}"
LEADING_INTEGER = r"(\d+)"
DECIMAL_WITH_SEPARATORS = r"([\d,]+(?:\.\d+)?)"


def normalise_name(value: str) -> str:
    """Name only — Excel stores name and address in one cell."""
    return re.split(NAME_SPLIT, value)[0].upper().strip(" ,")


def normalise_port(value: str) -> str:
    """Strip the UN/LOCODE. It is identical on both sides of every planted
    port defect, so it is a decoy, never the discriminator.

    The first segment only: a port read from a PDF form can pick up the line
    beneath it, which is the vessel.
    """
    first = re.split(NAME_SPLIT, value)[0]

    return LOCODE.sub("", first).upper().rstrip(",").strip()


def normalise_count(value: str) -> str | None:
    match = re.match(LEADING_INTEGER, value)

    return match.group(1) if match else None


def normalise_weight(value: str) -> str | None:
    match = re.search(DECIMAL_WITH_SEPARATORS, value)

    return str(float(match.group(1).replace(",", ""))) if match else None


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

    return {"field": field, "si_raw": si_raw, "bl_raw": bl_raw,
            "si_norm": si_norm, "bl_norm": bl_norm,
            "verdict": verdict_for(si_norm, bl_norm)}


