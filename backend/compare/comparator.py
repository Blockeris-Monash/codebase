"""Lane C - Stage 4: Document Comparison Engine.

Strictly compliant with ComparisonResult JSON Schema (Draft 2020-12).
No LLM/API dependencies: 100% deterministic local Python.
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.compare.evidence import describe_blanks, describe_unreadable, describe_wrong_doc
from backend.compare.normalise import SAME_AS_CONSIGNEE, normalise, same_container_count

# Distinguishes "no norm key at all" from "norm supplied as None".
_MISSING = object()

# The 7 canonical fields required by the contract
CANONICAL_FIELDS = [
    "shipper",
    "consignee",
    "notify_party",
    "port_of_loading",
    "port_of_discharge",
    "container_count",
    "gross_weight_kg",
]

FieldType = Literal[
    "shipper",
    "consignee",
    "notify_party",
    "port_of_loading",
    "port_of_discharge",
    "container_count",
    "gross_weight_kg",
]

VerdictType = Literal["match", "mismatch", "missing"]
StatusType = Literal["OK", "MISMATCH", "NEEDS_REVIEW"]
ReviewReasonType = Literal[
    "wrong_doc_type", "missing_attachment", "unreadable", "missing_value"
]


# =====================================================================
# Pydantic Output Contract (ComparisonResult)
# =====================================================================

class Row(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: FieldType
    si_raw: Optional[str] = None
    bl_raw: Optional[str] = None
    si_norm: Optional[str] = None
    bl_norm: Optional[str] = None
    verdict: VerdictType


RevisionLabelType = Literal["fixed", "still_wrong", "new_mistake", "unchanged"]


class RevisionRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: FieldType
    label: RevisionLabelType


class Revision(BaseModel):
    """A revised draft BL against the draft before it (#147 D1): each field's label comes from
    the SI checked against each draft. Evidence beside the verdict, never the verdict."""
    model_config = ConfigDict(extra="forbid")

    previous: str
    current: str
    previous_readable: bool
    rows: List[RevisionRow]


class ComparisonResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # email_NNN is the dataset; gmail_<id> is a message from the live mailbox (backend/gmail.py).
    email_id: str = Field(..., pattern=r"^(email_[0-9]{3}|gmail_[0-9a-f]{8,32}|upload_[0-9a-f]{12})$")
    status: StatusType
    review_reason: Optional[ReviewReasonType] = None
    rows: List[Row]
    defect_fields: List[FieldType]
    evidence: str
    # Only when the email carries a revised draft BL; absent otherwise, so contract 04 is unchanged for the rest.
    revision: Optional[Revision] = None

    @model_validator(mode="after")
    def keeps_the_contract_rules(self) -> "ComparisonResult":
        """Contract 04's if-and-only-if rules, so the service cannot build a result
        that breaks them (contracts/04-ComparisonResult.schema.json, allOf)."""
        if (self.status == "NEEDS_REVIEW") != (self.review_reason is not None):
            raise ValueError("status is NEEDS_REVIEW if and only if review_reason is set")
        if (self.status == "MISMATCH") != bool(self.defect_fields):
            raise ValueError("status is MISMATCH if and only if defect_fields is non-empty")
        return self


# =====================================================================
# Deterministic Normalization & Comparison Helpers
# =====================================================================

# A UN/LOCODE in brackets, "(KEMBA)", is always stripped.
LOCODE_DECOY = re.compile(r"\s*\(([A-Z]{5})\)\s*", re.I)
# A bare one, "CNSHA SHANGHAI", only when it starts with a real ISO 3166 country code. The
# old rule stripped every five-letter word, so KLANG, BUSAN and CHINA vanished and PORT
# KLANG matched PORT DICKSON (#147 A3). NORTH and SOUTH start with codes (Norway, Somalia)
# but are directions, and "MANILA NORTH HARBOUR" is not "MANILA SOUTH HARBOUR".
BARE_LOCODE = re.compile(r"\b[A-Z]{2}[A-Z0-9]{3}\b")
COUNTRY_CODES = frozenset("""
AD AE AF AG AI AL AM AO AQ AR AS AT AU AW AX AZ BA BB BD BE BF BG BH BI BJ BL BM BN BO BQ BR BS
BT BV BW BY BZ CA CC CD CF CG CH CI CK CL CM CN CO CR CU CV CW CX CY CZ DE DJ DK DM DO DZ EC EE
EG EH ER ES ET FI FJ FK FM FO FR GA GB GD GE GF GG GH GI GL GM GN GP GQ GR GS GT GU GW GY HK HM
HN HR HT HU ID IE IL IM IN IO IQ IR IS IT JE JM JO JP KE KG KH KI KM KN KP KR KW KY KZ LA LB LC
LI LK LR LS LT LU LV LY MA MC MD ME MF MG MH MK ML MM MN MO MP MQ MR MS MT MU MV MW MX MY MZ NA
NC NE NF NG NI NL NO NP NR NU NZ OM PA PE PF PG PH PK PL PM PN PR PS PT PW PY QA RE RO RS RU RW
SA SB SC SD SE SG SH SI SJ SK SL SM SN SO SR SS ST SV SX SY SZ TC TD TF TG TH TJ TK TL TM TN TO
TR TT TV TW TZ UA UG UM US UY UZ VA VC VE VG VI VN VU WF WS YE YT ZA ZM ZW
""".split())
NEVER_A_CODE = frozenset({"NORTH", "SOUTH"})
# Words that name a country (or part of one), not a place in it: the only words one side of a
# port may add or drop, as in "BUSAN" against "BUSAN, SOUTH KOREA". A country missing here is
# flagged for review rather than matched, which is the safe side to fail on.
COUNTRY_WORDS = frozenset("""
AFGHANISTAN ALBANIA ALGERIA ANGOLA ARGENTINA AUSTRALIA AUSTRIA BAHRAIN BANGLADESH BELGIUM BRAZIL
BRUNEI BULGARIA BURMA CAMBODIA CAMEROON CANADA CHILE CHINA COLOMBIA CROATIA CYPRUS CZECH DENMARK
DJIBOUTI ECUADOR EGYPT ESTONIA ETHIOPIA FINLAND FRANCE GERMANY GHANA GREECE GUINEA HONG KONG INDIA
INDONESIA IRAN IRAQ IRELAND ISRAEL ITALY IVORY COAST JAMAICA JAPAN JORDAN KENYA KOREA KUWAIT LATVIA
LEBANON LIBYA LITHUANIA MADAGASCAR MALAYSIA MALTA MAURITIUS MEXICO MOROCCO MOZAMBIQUE MYANMAR
NETHERLANDS NEW ZEALAND NIGERIA NORWAY OMAN PAKISTAN PANAMA PERU PHILIPPINES POLAND PORTUGAL QATAR
ROMANIA RUSSIA SAUDI ARABIA SENEGAL SINGAPORE SLOVENIA SPAIN SRI LANKA SUDAN SWEDEN SWITZERLAND
TAIWAN TANZANIA THAILAND TOGO TUNISIA TURKEY TURKIYE UKRAINE UNITED ARAB EMIRATES KINGDOM STATES
AMERICA URUGUAY VENEZUELA VIETNAM VIET NAM YEMEN ZAMBIA
NORTH SOUTH EAST WEST REPUBLIC OF THE PR UAE UK USA US KSA
""".split())


def is_bare_locode(token: str) -> bool:
    return token[:2] in COUNTRY_CODES and token not in NEVER_A_CODE


def extract_meaningful_tokens(val: str | None) -> set[str]:
    """Strips planted LOCODE decoys and returns uppercase alphanumeric tokens.

    A bare code goes only when a place other than a country is left without it: in
    "TOKYO, JAPAN" TOKYO is the city, not a code, even though TO is Tonga's code."""
    if not val:
        return set()
    words = set(re.findall(r"\b[A-Z0-9]{2,}\b", LOCODE_DECOY.sub("", val.upper())))
    rest = {w for w in words if not (BARE_LOCODE.fullmatch(w) and is_bare_locode(w))}
    return rest if rest - COUNTRY_WORDS else words


def same_place(a: set[str], b: set[str]) -> bool:
    """One side may add or drop only a country: BUSAN is BUSAN, SOUTH KOREA, but VIETNAM
    is not HO CHI MINH, VIETNAM, and JAPAN is not NAGOYA, JAPAN."""
    short, long = sorted((a, b), key=len)
    return short <= long and (long - short) <= COUNTRY_WORDS | COUNTRY_CODES   # "SHANGHAI, CN"


def compare_single_field(
    field: str, si_norm: Optional[str], bl_norm: Optional[str]
) -> VerdictType:
    """Computes exact schema verdict: 'match', 'mismatch', or 'missing'."""
    # A field with a missing or blank normalized value on either side is missing
    if si_norm is None or bl_norm is None:
        return "missing"
    if str(si_norm).strip() == "" or str(bl_norm).strip() == "":
        return "missing"

    s_norm = str(si_norm).strip().upper()
    b_norm = str(bl_norm).strip().upper()

    # Fast path: exact string identity
    if s_norm == b_norm:
        return "match"

    # 1. Weights: numerical comparison with float tolerance
    if field == "gross_weight_kg":
        try:
            val_si = float(s_norm.replace(",", ""))
            val_bl = float(b_norm.replace(",", ""))
            return "match" if abs(val_si - val_bl) <= 0.1 else "mismatch"
        except (ValueError, TypeError):
            return "mismatch"

    # 2. Container Count: per size when broken down by size, else the total
    if field == "container_count":
        return "match" if same_container_count(s_norm, b_norm) else "mismatch"

    # 3. Ports: the same words in any order, or one side adding only the country
    if field in {"port_of_loading", "port_of_discharge"}:
        si_tokens = extract_meaningful_tokens(s_norm)
        bl_tokens = extract_meaningful_tokens(b_norm)
        if si_tokens and bl_tokens and same_place(si_tokens, bl_tokens):
            return "match"

    return "mismatch"


# =====================================================================
# Main Comparison Runner
# =====================================================================

# (wrong in the previous draft, wrong in this one) -> label, where right means the verdict is match.
REVISION_LABELS: Dict[tuple[bool, bool], RevisionLabelType] = {
    (True, False): "fixed", (True, True): "still_wrong", (False, True): "new_mistake", (False, False): "unchanged"}


def revision_between(previous: ComparisonResult, current: ComparisonResult,
                     previous_name: str, current_name: str) -> Revision:
    """Each field's label, from the SI against the previous draft and against this one. A
    previous draft that could not be compared field by field gets no labels."""
    before = {row.field: row.verdict != "match" for row in previous.rows}
    after = {row.field: row.verdict != "match" for row in current.rows}
    readable = len(before) == len(CANONICAL_FIELDS)
    rows = [RevisionRow(field=field, label=REVISION_LABELS[(before[field], after[field])])
            for field in CANONICAL_FIELDS if readable and field in after]

    return Revision(previous=previous_name, current=current_name, previous_readable=readable, rows=rows)


def with_notify_resolved(fields: Dict[str, Any]) -> Dict[str, Any]:
    """`fields` with a SAME AS CONSIGNEE notify party compared as that document's consignee.
    Its raw value is kept, so the screen still shows what the document says."""
    notify, consignee = fields.get("notify_party") or {}, fields.get("consignee") or {}
    if not SAME_AS_CONSIGNEE.match(str(notify.get("raw") or "")):
        return fields
    norm = consignee["norm"] if "norm" in consignee else normalise("consignee", consignee.get("raw"))

    return {**fields, "notify_party": {**notify, "norm": norm}}


def compare(
    email_id: str,
    si_doc: Optional[Dict[str, Any]],
    bl_doc: Optional[Dict[str, Any]],
) -> ComparisonResult:
    """Consumes SI & BL extractions and returns the validated ComparisonResult."""
    # Pre-check 1: Missing attachment
    if si_doc is None or bl_doc is None:
        missing_doc = "SI" if si_doc is None else "BL"
        return ComparisonResult(
            email_id=email_id,
            status="NEEDS_REVIEW",
            review_reason="missing_attachment",
            rows=[],
            defect_fields=[],
            evidence=f"Missing attachment: {missing_doc} document was not provided.",
        )

    # Pre-check 2: Unreadable. This comes before the document-type check
    # because a file that would not open has no title to read, so its type
    # is unknown rather than wrong. Emails 511-515 are exactly this case.
    if si_doc.get("parse_status") != "ok" or bl_doc.get("parse_status") != "ok":
        return ComparisonResult(
            email_id=email_id,
            status="NEEDS_REVIEW",
            review_reason="unreadable",
            rows=[],
            defect_fields=[],
            evidence=describe_unreadable(si_doc.get("parse_status"), bl_doc.get("parse_status")),
        )

    # Pre-check 3: Wrong document type
    if si_doc.get("detected_doc_type") != "SI" or bl_doc.get("detected_doc_type") != "BL":
        return ComparisonResult(
            email_id=email_id,
            status="NEEDS_REVIEW",
            review_reason="wrong_doc_type",
            rows=[],
            defect_fields=[],
            evidence=describe_wrong_doc(si_doc.get("detected_doc_type"),
                                        bl_doc.get("detected_doc_type")),
        )


    # Build the 7 comparison rows
    rows: List[Row] = []
    defect_fields: List[FieldType] = []
    missing_fields: List[str] = []
    # (field, si_raw, bl_raw, si_absent, bl_absent) - the token a blank used is the
    # difference between chasing a value and rejecting a form, so it is kept.
    blanks: List[tuple] = []

    # `or {}`, not a default: a key present as null is None, and treated as absent.
    si_fields = with_notify_resolved(si_doc.get("fields") or {})
    bl_fields = with_notify_resolved(bl_doc.get("fields") or {})

    for field_name in CANONICAL_FIELDS:
        si_item = si_fields.get(field_name) or {}
        bl_item = bl_fields.get(field_name) or {}

        si_raw = si_item.get("raw")
        bl_raw = bl_item.get("raw")
        # Contract 03 supplies `raw` only. Extraction leaves values exactly as
        # written so the review screen can show source evidence; normalising
        # is this stage's job. Fall back to a supplied `norm` if a caller
        # happens to pre-normalise.
        si_norm = si_item.get("norm", _MISSING)
        bl_norm = bl_item.get("norm", _MISSING)
        if si_norm is _MISSING:
            si_norm = normalise(field_name, si_raw)
        if bl_norm is _MISSING:
            bl_norm = normalise(field_name, bl_raw)

        verdict = compare_single_field(field_name, si_norm, bl_norm)
        # A norm can be the total alone; the per-size breakdown is in what was written.
        if field_name == "container_count" and verdict != "missing" and si_raw and bl_raw:
            verdict = "match" if same_container_count(str(si_raw), str(bl_raw)) else "mismatch"

        if verdict == "mismatch":
            defect_fields.append(field_name)  # type: ignore
        elif verdict == "missing":
            missing_fields.append(field_name)
            si_absent = si_norm is None or not str(si_norm).strip()
            bl_absent = bl_norm is None or not str(bl_norm).strip()
            blanks.append((field_name, si_raw, bl_raw, si_absent, bl_absent))

        rows.append(
            Row(
                field=field_name,  # type: ignore
                si_raw=str(si_raw) if si_raw is not None else None,
                bl_raw=str(bl_raw) if bl_raw is not None else None,
                si_norm=str(si_norm) if si_norm is not None else None,
                bl_norm=str(bl_norm) if bl_norm is not None else None,
                verdict=verdict,
            )
        )

    # Priority Rule 1: Any missing values trigger NEEDS_REVIEW
    if missing_fields:
        return ComparisonResult(
            email_id=email_id,
            status="NEEDS_REVIEW",
            review_reason="missing_value",
            rows=rows,
            defect_fields=[],  # Schema specifies defect_fields empty unless status == MISMATCH
            evidence=describe_blanks(blanks),
        )

    # Priority Rule 2: Hard discrepancies trigger MISMATCH
    if defect_fields:
        return ComparisonResult(
            email_id=email_id,
            status="MISMATCH",
            review_reason=None,  # Must be null if status != NEEDS_REVIEW
            rows=rows,
            defect_fields=defect_fields,
            evidence=f"Discrepancies found in {len(defect_fields)} field(s): {', '.join(defect_fields)}.",
        )

    # Priority Rule 3: Complete clean match
    return ComparisonResult(
        email_id=email_id,
        status="OK",
        review_reason=None,
        rows=rows,
        defect_fields=[],
        evidence="No mismatch detected. All 7 fields match between SI and BL.",  # the brief's wording
    )


# =====================================================================
# Verification Unit Tests for email_517 (NEEDS_REVIEW Case)
# =====================================================================

if __name__ == "__main__":
    # Extracted and normalized from email_517_SI.txt
    si_input_517 = {
        "email_id": "email_517",
        "detected_doc_type": "SI",
        "parse_status": "ok",
        "fields": {
            "shipper": {
                "raw": "APRIL FAR EAST (M) SDN BHD",
                "norm": "APRIL FAR EAST (M) SDN BHD",
            },
            "consignee": {
                "raw": "BALL & DOGGETT AUSTRALIA PTY LTD",
                "norm": "BALL & DOGGETT AUSTRALIA PTY LTD",
            },
            "notify_party": {
                "raw": "BALL & DOGGETT AUSTRALIA PTY LTD",
                "norm": "BALL & DOGGETT AUSTRALIA PTY LTD",
            },
            "port_of_loading": {
                "raw": "____MT",
                "norm": None,  # Blank placeholder normalizes to null
            },
            "port_of_discharge": {
                "raw": "TBA",
                "norm": None,  # TBA normalizes to null
            },
            "container_count": {
                "raw": "15 x 20'GP",
                "norm": "15 X 20'GP",
            },
            "gross_weight_kg": {
                "raw": "340,770 KG",
                "norm": "340770",
            },
        },
    }

    # Extracted and normalized from email_517_BL.txt
    bl_input_517 = {
        "email_id": "email_517",
        "detected_doc_type": "BL",
        "parse_status": "ok",
        "fields": {
            "shipper": {
                "raw": "APRIL FAR EAST (M) SDN BHD\n  TOWER 2, AVENUE 5, LEVEL 6; BANGSAR SOUTH CITY, NO. 8 JALAN KERINCHI; 59200 KUALA LUMPUR, MALAYSIA",
                "norm": "APRIL FAR EAST (M) SDN BHD",
            },
            "consignee": {
                "raw": "BALL & DOGGETT AUSTRALIA PTY LTD\n  43-45 METROPOLITAN ROAD; ENFIELD NSW 2136, AUSTRALIA",
                "norm": "BALL & DOGGETT AUSTRALIA PTY LTD",
            },
            "notify_party": {
                "raw": "BALL & DOGGETT AUSTRALIA PTY LTD",
                "norm": "BALL & DOGGETT AUSTRALIA PTY LTD",
            },
            "port_of_loading": {
                "raw": "SINGAPORE (SGSIN)",
                "norm": "SINGAPORE",
            },
            "port_of_discharge": {
                "raw": "CALLAO, PERU (PECLL)",
                "norm": "CALLAO, PERU",
            },
            "container_count": {
                "raw": "15 x 20'GP",
                "norm": "15 X 20'GP",
            },
            "gross_weight_kg": {
                "raw": "340,770 KG",
                "norm": "340770",
            },
        },
    }

    result = compare("email_517", si_input_517, bl_input_517)
    print("Schema Output for email_517:")
    print(json.dumps(result.model_dump(), indent=2))