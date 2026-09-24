"""Pipeline Orchestrator: Ingests document pairs, extracts via AI (Qwen/Cached),
cleans fields, and runs deterministic comparison.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, Query, Response
from pydantic import BaseModel, Field

# Import Milk's Extractor and Model
from backend.classify import ClassificationFailed, ClassificationResult, EmailInput, classify_email
from backend.extract.ai import AiExtractor
from backend.extract.fallback import with_fallback
from backend.extract.gemini import api_key as gemini_key, gemini_model
from backend.extract.qwen import qwen_model

# Import JJ's Deterministic Comparator
from backend.compare.comparator import ComparisonResult, compare
from backend import gmail, reports
from backend.compare.normalise import NAME_SPLIT  # one rule for where a name ends, shared with the reference
from backend.contracts import DocumentRoleType, ParseStatusType, StatusType
from backend.read.labels import detect_doc_type
from backend.translate import TooMuchText, TranslationFailed, translate_texts
from backend.read.documents import document_title, read_document
from backend.logging_setup import configure as configure_logging


load_dotenv()
# Before anything else logs: without this every log.info in the service is
# discarded and the warnings that survive carry no timestamp or request id.
configure_logging()
log = logging.getLogger(__name__)

app = FastAPI(title="Document Discrepancy Orchestrator")

from fastapi.middleware.cors import CORSMiddleware

from backend.middleware import tag_and_limit

# Enable CORS so Han's Vercel frontend can talk to Render
cors_env = os.environ.get("CORS_ORIGINS", "*")
allowed_origins = [o.strip() for o in cors_env.split(",") if o.strip()] if cors_env != "*" else ["*"]

# A request id on every answer, and a ceiling on how fast the model routes can
# be called - the URL is public and one ?live=true press spends two Qwen calls.
app.middleware("http")(tag_and_limit)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    # No cookies and no auth header on any route here, so allow_credentials is False.
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    # The page is on another site, so the browser hides any response header not named here.
    expose_headers=["X-Mailbox-Pending"],
)

class Health(BaseModel):
    status: str


@app.api_route("/health", methods=["GET", "HEAD"], response_model=Health)
def health_check():
    """Lightweight endpoint for UptimeRobot and cloud health checkers."""
    return {"status": "ok"}


# Directory where Milk's pre-extracted results are stored
ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "data"
EXTRACTS_DIR = ROOT_DIR / "results" / "extracts"

FIELD_NAMES = [
    "shipper",
    "consignee",
    "notify_party",
    "port_of_loading",
    "port_of_discharge",
    "container_count",
    "gross_weight_kg",
]

SENTINEL = re.compile(r"^\s*$|^(n/?a|tba|tbc|-+)$|^_+\s*\w*$", re.I)

# =====================================================================
# 1. Input/Output Request Models
# =====================================================================

class PairedInput(BaseModel):
    email_id: str
    si_pairs: List[tuple[str, str]]
    bl_pairs: List[tuple[str, str]]
    # The reader saw the document's own header and knows whether the file
    # opened. Neither can be recovered from the pairs - a .txt SI leads with
    # Shipper, not with its title - and the comparator escalates any document
    # whose type or parse status is unknown, so the caller has to say.
    si_title: Optional[str]
    bl_title: Optional[str]
    si_parse_status: str = ParseStatusType.Ok
    bl_parse_status: str = ParseStatusType.Ok


# =====================================================================
# 2. Stage 3 Extraction: Hybrid (Pre-computed Cache + Live Qwen AI)
# =====================================================================

# Qwen first. If it fails or stalls, Gemini answers (with_fallback), but only when a Gemini key
# is set: without one, Qwen is used exactly as before, however slow it is. With a second
# provider behind, two tries are enough.
extractor = AiExtractor(with_fallback(qwen_model, gemini_model, enabled=lambda: bool(gemini_key())),
                        tries=2)

def load_saved_extract(email_id: str, role: str) -> Optional[Dict[str, Any]]:
    """The whole cached DocumentExtract, metadata included.

    Returning only `fields` drops parse_status and detected_doc_type, and the
    comparator escalates any document missing them - which was every document,
    so every email came back NEEDS_REVIEW/unreadable.
    """
    extract_file = EXTRACTS_DIR / f"{email_id}_{role}.json"
    if not extract_file.exists():
        return None

    try:
        return json.loads(extract_file.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        log.warning("Failed to load cached extract for %s: %s", extract_file.name, error)
        return None

ABSENT_FIELDS = {"present": False, "raw": None, "label_seen": None}


async def extract_live(
    email_id: str,
    role: str,
    pairs: List[tuple[str, str]],
    title: Optional[str],
    parse_status: str,
) -> Dict[str, Any]:
    """One document through Milk's AiExtractor, shaped as a DocumentExtract.

    Run in a threadpool so the SI and the BL extract concurrently.
    """
    try:
        with reports.watching(f"Extraction ({role})", email_id,
                              "Every field was treated as missing, so the email went to a person."):
            raw_fields = await asyncio.to_thread(extractor.extract_fields, email_id, pairs)
    except Exception as error:  # third-party model client, any failure is one
        log.error("Live extraction failed for %s (%s): %s", email_id, role, error)
        raw_fields = None

    if not raw_fields:
        # A model that returned nothing is not evidence that the fields are
        # absent, so every field is marked missing and the comparator sends
        # the pair to a human rather than calling it a match.
        raw_fields = {field: dict(ABSENT_FIELDS) for field in FIELD_NAMES}

    return {
        "email_id": email_id,
        "declared_role": role,
        "detected_doc_type": detect_doc_type(title) if title else None,
        "parse_status": parse_status,
        "fields": raw_fields,
    }


def is_cache_current(cached: Dict[str, Any], title: Optional[str],
                     parse_status: str) -> bool:
    """Whether a saved extract describes the document the caller actually sent.

    The cache is keyed on (email_id, role) alone, so on its own it cannot tell
    "the same document again" from "a different document under the same id" -
    and it used to win either way, silently discarding the pairs, the title and
    the parse status the caller was asked to supply. A caller reporting a file
    that would not open, or a title that resolves to another document type, is
    describing something this record does not hold.
    """
    if parse_status != cached.get("parse_status"):
        return False
    if title is None:
        return True

    return detect_doc_type(title) == cached.get("detected_doc_type")


async def extract_document(
    email_id: str,
    role: str,
    pairs: List[tuple[str, str]],
    title: Optional[str],
    parse_status: str,
) -> Dict[str, Any]:
    """Cache first, model second. Milk's saved results answer instantly."""
    cached = load_saved_extract(email_id, role)
    if cached and is_cache_current(cached, title, parse_status):
        return cached

    return await extract_live(email_id, role, pairs, title, parse_status)


# =====================================================================
# 3. Normalization: contract 03 fields into comparable form (stage 4's front half)
# =====================================================================

def clean_entity(text: str) -> str:
    """Takes only the entity name before any address pipe ' | '."""
    first_segment = re.split(NAME_SPLIT, text)[0]
    return re.sub(r"\s+", " ", first_segment).upper().strip(" ,.;:")

def clean_port(text: str) -> str:
    first_segment = re.split(NAME_SPLIT, text)[0]
    # Remove UN/LOCODE in parentheses e.g. (MYPKG)
    text_no_locode = re.sub(r"\s*\(\s*[A-Z0-9]{5}\s*\)", "", first_segment, flags=re.I)
    return re.sub(r"\s+", " ", text_no_locode).upper().strip(" ,.;:")

def clean_containers(text: str) -> str:
    text = text.upper().strip()
    return re.sub(r"\s*X\s*", " x ", text)

def clean_weight(text: str) -> str:
    text_upper = text.upper()
    is_mt = "MT" in text_upper or "M/T" in text_upper
    numeric_str = re.sub(r"[^\d.]", "", text.replace(",", ""))
    if not numeric_str:
        return ""
    try:
        weight_val = float(numeric_str)
        if is_mt:
            weight_val *= 1000.0
        return str(weight_val)
    except ValueError:
        return text.strip()

def apply_cleaner(fields: Dict[str, Any]) -> Dict[str, Any]:
    cleaned: Dict[str, Any] = {}
    for key in FIELD_NAMES:
        field_data = fields.get(key, {"present": False, "raw": None})
        raw_text = field_data.get("raw")
        present = field_data.get("present", False)

        if not present or not raw_text or SENTINEL.match(str(raw_text).strip()):
            field_data["norm"] = None
        else:
            raw_str = str(raw_text).strip()
            if key in ["shipper", "consignee", "notify_party"]:
                field_data["norm"] = clean_entity(raw_str)
            elif key in ["port_of_loading", "port_of_discharge"]:
                field_data["norm"] = clean_port(raw_str)
            elif key == "container_count":
                field_data["norm"] = clean_containers(raw_str)
            elif key == "gross_weight_kg":
                field_data["norm"] = clean_weight(raw_str)
            else:
                field_data["norm"] = raw_str

        cleaned[key] = field_data
    return cleaned


# =====================================================================
# 4. FastAPI Endpoint: Extract -> Clean -> Compare
# =====================================================================

@app.post("/extract-clean-compare", response_model=ComparisonResult)
async def run_pipeline(
    payload: PairedInput,
    live: bool = Query(
        False, description="Set to true to force live Qwen AI call instead of loading saved extracts"
    ),
):
    """Orchestrates the full flow:
    1. Extracts SI & BL concurrently using Milk's AiExtractor (Hybrid mode).
    2. Cleans & normalizes values into standard comparable formats.
    3. Evaluates discrepancies using JJ's deterministic engine.
    """
    # 1. Concurrently extract SI and BL
    extract = extract_live if live else extract_document
    si_extract, bl_extract = await asyncio.gather(
        extract(payload.email_id, DocumentRoleType.Si, payload.si_pairs,
                payload.si_title, payload.si_parse_status),
        extract(payload.email_id, DocumentRoleType.Bl, payload.bl_pairs,
                payload.bl_title, payload.bl_parse_status),
    )

    # 2. Clean & normalize, keeping the metadata the comparator prechecks on
    # A document that was never found is None, not one that failed to parse.
    # The comparator's first precheck is what turns that into
    # missing_attachment rather than the misleading unreadable.
    si_doc = None if payload.si_parse_status == ParseStatusType.Missing else {
        **si_extract, "fields": apply_cleaner(si_extract["fields"])}
    bl_doc = None if payload.bl_parse_status == ParseStatusType.Missing else {
        **bl_extract, "fields": apply_cleaner(bl_extract["fields"])}

    # 3. Deterministic comparison (JJ's Engine)
    report = compare(payload.email_id, si_doc, bl_doc)

    return report


# --- classification (Hanif's, lifted out of its own server) -------------

# --- translation for the UI's Translate button --------------------------

class TranslateRequest(BaseModel):
    # A free-text target is interpolated straight into the prompt, so a caller
    # could send instructions dressed as a language. The UI only ever offers
    # these three.
    target: Literal["English", "Malay", "Chinese"]
    texts: Dict[str, str]


class TranslateResponse(BaseModel):
    texts: Dict[str, str]


@app.post("/translate", response_model=TranslateResponse)
async def translate(request: TranslateRequest) -> TranslateResponse:
    """The email and its documents translated into one language."""
    try:
        return TranslateResponse(texts=await asyncio.to_thread(translate_texts, request.texts, request.target))
    except TooMuchText as error:
        raise HTTPException(status_code=413, detail=str(error)) from error
    except (TranslationFailed, RuntimeError) as error:
        raise HTTPException(status_code=502, detail=str(error)) from error


@app.post("/classify", response_model=ClassificationResult)
async def classify(email: EmailInput) -> ClassificationResult:
    """One email in, one ClassificationResult out. Contract 02."""
    try:
        return await classify_email(email)
    except ClassificationFailed as error:
        raise HTTPException(status_code=502, detail=str(error)) from error

# =====================================================================
# 5. Routing Helpers: Attachment Resolution
# =====================================================================

def resolve_attachment_path(att_path_str: str) -> Optional[Path]:
    """Finds the attachment file in data/attachments/ or local paths."""
    p = Path(att_path_str)
    if p.is_absolute() and p.exists():
        return p
    # Look inside data/attachments/<filename>
    direct = DATA_DIR / "attachments" / p.name
    if direct.exists():
        return direct
    # Look inside data/<relative_path>
    relative = DATA_DIR / att_path_str
    if relative.exists():
        return relative
    return None


def read_paired_attachments(email: EmailInput) -> PairedInput:
    """Locates SI and BL attachments, reads label/value pairs, and records parse status."""
    si_path_str = next(
        (a for a in email.attachments if f"_{DocumentRoleType.Si}." in a or a.upper().endswith("SI")),
        None,
    )
    bl_path_str = next(
        (a for a in email.attachments if f"_{DocumentRoleType.Bl}." in a or a.upper().endswith("BL")),
        None,
    )

    return read_pair(email.email_id, si_path_str, bl_path_str)


def read_pair(email_id: str, si_path_str: Optional[str], bl_path_str: Optional[str]) -> PairedInput:
    """Reads one SI and one BL (either may be absent) into the pipeline's input."""
    si_file = resolve_attachment_path(si_path_str) if si_path_str else None
    bl_file = resolve_attachment_path(bl_path_str) if bl_path_str else None

    # Read SI
    if si_file and si_file.exists():
        si_status, si_pairs = read_document(si_file)
        si_title = document_title(si_file)
    else:
        si_status, si_pairs, si_title = ParseStatusType.Missing, [], None

    # Read BL
    if bl_file and bl_file.exists():
        bl_status, bl_pairs = read_document(bl_file)
        bl_title = document_title(bl_file)
    else:
        bl_status, bl_pairs, bl_title = ParseStatusType.Missing, [], None

    return PairedInput(
        email_id=email_id,
        si_pairs=si_pairs,
        bl_pairs=bl_pairs,
        si_title=si_title,
        bl_title=bl_title,
        si_parse_status=si_status,
        bl_parse_status=bl_status,
    )


# One email can carry more than one shipment: email_SI.txt with email_BL.txt, and
# email_SI_2.txt with email_BL_2.txt. Reading only the first pair let a defect in the
# second pass as OK (tests/edge_cases, a8).
ROLE_IN_NAME = re.compile(rf"_({DocumentRoleType.Si}|{DocumentRoleType.Bl})(?=[._])")
# A gap outranks a mismatch, so the person sees it first; OK only when every shipment is.
SEVERITY = {StatusType.Ok: 0, StatusType.Mismatch: 1, StatusType.NeedsReview: 2}


def shipments(attachments: List[str]) -> List[tuple[str, str]]:
    """(SI, BL) for every shipment that has both, matched by the rest of the file name."""
    groups: Dict[str, Dict[str, str]] = {}
    for path in attachments:
        name = Path(path).name
        role = ROLE_IN_NAME.search(name)
        if role:
            key = Path(ROLE_IN_NAME.sub("", name, count=1)).stem  # email_SI_2.txt -> email_2
            groups.setdefault(key, {}).setdefault(role.group(1), path)
    return [(g[DocumentRoleType.Si], g[DocumentRoleType.Bl])
            for g in groups.values() if len(g) == 2]


async def compare_email(email: EmailInput, live: bool = False):
    """The comparison for one email. With two or more complete SI and BL pairs, each is
    compared and the most severe result is returned, its evidence naming every shipment.
    Anything else goes through read_paired_attachments exactly as before."""
    pairs = shipments(email.attachments)
    if len(pairs) < 2:
        return await run_pipeline(read_paired_attachments(email), live=live)

    results = [await run_pipeline(read_pair(email.email_id, si, bl), live=live) for si, bl in pairs]
    worst = max(range(len(results)), key=lambda i: SEVERITY[results[i].status])
    summary = ", ".join(f"shipment {i + 1} {r.status}" for i, r in enumerate(results))
    evidence = f"{len(results)} shipments in this email ({summary}); showing shipment {worst + 1}."
    detail = results[worst].evidence
    return results[worst].model_copy(update={"evidence": f"{evidence} {detail}" if detail else evidence})


# =====================================================================
# 6. Master Route: Classify -> Route (Compare or Pass-Through)
# =====================================================================

class SubmissionEntryOut(BaseModel):
    """The line that reaches the organisers' scorer. Named so a change to it is
    a visible change to a contract, not an edit to a dict literal."""
    category: str
    status: str
    review_reason: Optional[str] = None
    has_defect: bool
    defect_fields: List[str]


class ProcessedEmail(BaseModel):
    """What /process-email answers with. It returned Dict[str, Any], so nothing
    checked the shape and the five people integrating against it had only the
    source to go on."""
    email_id: str
    EmailRecord: Dict[str, Any]
    ClassificationResult: Dict[str, Any]
    ComparisonResult: Optional[Dict[str, Any]] = None
    SubmissionEntry: SubmissionEntryOut
    # A reply drafted from company policy for INVOICE_QUERY and GENERAL mail (#93), or None.
    # Kept out of SubmissionEntry so the scorer's line keeps exactly its five keys.
    draft_reply: Optional[str] = None



@app.post("/process-email", response_model=ProcessedEmail)
async def process_email(
    email: EmailInput,
    live: bool = Query(
        False, description="Set to true to force live Qwen AI calls instead of cached extracts"
    ),
) -> Dict[str, Any]:
    """1-Click End-to-End Entrypoint:
    1. Classifies email category.
    2. Routes BL_COMPARISON to document extraction and comparison.
    3. Passes through non-comparison emails with null ComparisonResult.
    """
    # 1. Classify the email
    classification = await classify(email)

    # 2. Build standard EmailRecord structure
    sender_domain = email.from_email.split("@")[-1] if "@" in email.from_email else ""
    email_record = {
        "email_id": email.email_id,
        "from": email.from_email,
        "sender_domain": sender_domain,
        "subject": email.subject,
        "body": email.body,
        "attachments": email.attachments,
    }

    # 3. Non-comparison branch (SI_REQUEST, INVOICE_QUERY, GENERAL, SPAM)
    if classification.category != "BL_COMPARISON":
        draft_reply = None
        if classification.category in ("INVOICE_QUERY", "GENERAL"):
            from backend.reply import generate_rag_reply
            # A thread, not a direct call: it waits on the AI for up to 120 s, and a blocking
            # call here would stop every other request (#96).
            draft_reply = await asyncio.to_thread(generate_rag_reply, email, classification.category)

        return {
            "email_id": email.email_id,
            "EmailRecord": email_record,
            "ClassificationResult": classification.model_dump(),
            "ComparisonResult": None,
            "SubmissionEntry": {
                "category": classification.category,
                "status": "OK",
                "review_reason": None,
                "has_defect": False,
                "defect_fields": [],
            },
            "draft_reply": draft_reply,
        }

    # 4. BL_COMPARISON branch: resolve attachments & run comparison pipeline
    comparison = await compare_email(email, live=live)

    comparison_dict = comparison.model_dump() if hasattr(comparison, "model_dump") else comparison

    return {
        "email_id": email.email_id,
        "EmailRecord": email_record,
        "ClassificationResult": classification.model_dump(),
        "ComparisonResult": comparison_dict,
        "SubmissionEntry": {
            "category": classification.category,
            "status": comparison_dict.get("status", "OK"),
            "review_reason": comparison_dict.get("review_reason"),
            "has_defect": bool(comparison_dict.get("defect_fields")),
            "defect_fields": comparison_dict.get("defect_fields", []),
        },
    }


# =====================================================================
# 7. Live mailbox (task 2): read the signed-in person's Gmail, reply from it
# =====================================================================
#
# Both routes take the person's Google access token as `Authorization: Bearer`,
# use it for that request and keep nothing of it (backend/gmail.py says why).
# Whose mailbox it is comes from Google, from the token itself, never from a
# user id the caller supplies: a caller cannot ask for anyone else's mail.

MAILBOX_DIR = Path(os.environ.get("MAILBOX_DIR", "/tmp/shiphappens-mailbox"))
MAILBOXES: Dict[str, Dict[str, Dict[str, Any]]] = {}   # address -> gmail id -> inbox entry
ORIGINALS: Dict[str, Dict[str, gmail.Message]] = {}    # address -> gmail id -> what a reply threads under
WORKING: Dict[tuple[str, str], asyncio.Task] = {}       # (address, gmail id) being checked now
FAILURES: Dict[tuple[str, str], int] = {}
GIVE_UP_AFTER = 2
# Two at a time: the model proxy slows to a crawl under more, and the page polls every 10 s.
CHECKS = asyncio.Semaphore(2)


def bearer(authorization: Optional[str]) -> str:
    token = (authorization or "").removeprefix("Bearer ").strip()
    if not token or token == authorization:
        raise HTTPException(status_code=401, detail="Sign in with Google to use your mailbox.")
    return token


def gmail_failure(error: gmail.GmailError) -> HTTPException:
    if error.status in (401, 403):
        # 401: the hour is up. 403: signed in before the app asked for Gmail access.
        return HTTPException(status_code=401, detail="Sign in with Google again to use your mailbox.")
    if error.status == 404:
        return HTTPException(status_code=404, detail="That email is not in your mailbox.")
    return HTTPException(status_code=502, detail=str(error))


def folder_for(address: str, gmail_id: str) -> Path:
    import hashlib
    return MAILBOX_DIR / hashlib.sha256(address.encode()).hexdigest()[:16] / gmail_id


async def mailbox_entry(message: gmail.Message, paths: List[str]) -> Dict[str, Any]:
    """One live email as the page draws it: the same fields cli/make_results.py
    writes for a demo email, from the same /process-email the demo button calls."""
    from cli.make_results import clean_body, document, shipment_ref  # cli imports this module

    email_id = gmail.mailbox_id(message.gmail_id)
    email = EmailInput(email_id=email_id, from_email=message.sender[:255], subject=message.subject[:1000],
                       body=message.body[:100_000], attachments=paths[:50])
    checked = await process_email(email, live=True)
    found = checked["ClassificationResult"]

    entry = {"id": email_id, "from": message.sender, "subject": message.subject,
             "body": clean_body(message.body), "n_attachments": len(paths), "received_at": message.date,
             "category": found["category"], "decided_by": found["decided_by"],
             "class_confidence": found["confidence"], "class_evidence": found["evidence"],
             "draft_reply": checked.get("draft_reply")}
    ref = shipment_ref(message.subject, message.body)
    if ref:
        entry["ref"] = ref

    result = checked["ComparisonResult"]
    if result:
        docs = {}
        for path in map(Path, paths):
            for role in (DocumentRoleType.Si, DocumentRoleType.Bl):
                if path.stem == f"{email_id}_{role}":
                    docs[role] = document(path, email_id, role)
        entry.update(status=result["status"], review_reason=result["review_reason"], rows=result["rows"],
                     defect_fields=result["defect_fields"], evidence=result["evidence"], docs=docs)
    return entry


async def check_message(token: str, address: str, gmail_id: str) -> None:
    """Fetch one message and its attachments, put it through /process-email, and
    keep the result. Runs behind the request, so the page never waits on a model."""
    key = (address, gmail_id)
    try:
        async with CHECKS:
            async with gmail.Gmail(token) as box:
                message = await box.message(gmail_id)
                files = await box.attachment_files(message)
            email_id = gmail.mailbox_id(gmail_id)
            paths = gmail.save_attachments(email_id, files, folder_for(address, gmail_id))
            entry = await mailbox_entry(message, paths)
        message.attachments = []  # a reply needs the headers, not the files
        ORIGINALS.setdefault(address, {})[gmail_id] = message
        MAILBOXES.setdefault(address, {})[gmail_id] = entry
    except Exception as error:  # a model, Gmail or a file: any of them, and the next poll retries
        FAILURES[key] = FAILURES.get(key, 0) + 1
        log.warning("Mailbox message %s not checked (try %d): %s", gmail_id, FAILURES[key], error)
        if FAILURES[key] >= GIVE_UP_AFTER:
            # Shown under Other mail rather than retried forever, one model bill per poll.
            MAILBOXES.setdefault(address, {})[gmail_id] = {
                "id": gmail.mailbox_id(gmail_id), "from": "", "subject": "(could not be checked)",
                "body": "This email could not be read or checked. Open it in Gmail.",
                "n_attachments": 0, "check_failed": True}
    finally:
        WORKING.pop(key, None)


@app.get("/mailbox")
async def mailbox(response: Response, authorization: Optional[str] = Header(None)) -> List[Dict[str, Any]]:
    """The newest emails in the signed-in person's inbox, each already checked, newest
    first. A message not yet checked is started in the background and appears on a
    later poll; `X-Mailbox-Pending` says how many are still being checked. A message
    is checked once: a second poll returns the saved result, not a second copy."""
    token = bearer(authorization)
    try:
        async with gmail.Gmail(token) as box:
            address = await box.address()
            ids = await box.recent_ids()
    except gmail.GmailError as error:
        raise gmail_failure(error) from error

    done = MAILBOXES.setdefault(address, {})
    for gmail_id in ids:
        key = (address, gmail_id)
        if gmail_id not in done and key not in WORKING:
            WORKING[key] = asyncio.create_task(check_message(token, address, gmail_id))

    response.headers["X-Mailbox-Pending"] = str(sum(1 for a, _ in WORKING if a == address))
    return [done[g] for g in ids if g in done]


class ReplyRequest(BaseModel):
    email_id: str = Field(..., max_length=100)
    to: str = Field(..., max_length=320)
    subject: str = Field(..., max_length=1000, pattern=r"^[^\r\n]*$")  # a line break would start a new header
    body: str = Field(..., min_length=1, max_length=20_000)


def one_address(to: str) -> str:
    """Exactly one recipient, as typed or as "Name <address>". The page drafts the
    reply to the sender; anything else here is a mistake, not a mailing list."""
    from email.utils import getaddresses
    found = getaddresses([to])
    if "\r" in to or "\n" in to or len(found) != 1 or "@" not in found[0][1]:
        raise HTTPException(status_code=422, detail="Send to one email address.")
    return to.strip()


@app.post("/reply")
async def reply(request: ReplyRequest, authorization: Optional[str] = Header(None)) -> Dict[str, Any]:
    """Send the reviewer's reply from their own Gmail, in the same thread as the email
    it answers. Only a person pressing Send reaches this: nothing is sent on its own."""
    token = bearer(authorization)
    gmail_id = gmail.gmail_id_of(request.email_id)
    if gmail_id is None:
        raise HTTPException(status_code=404, detail="Only emails from your own mailbox can be answered from here.")
    to = one_address(request.to)
    try:
        async with gmail.Gmail(token) as box:
            address = await box.address()
            # Fetched again when not seen here: that also proves the email is in THIS mailbox.
            original = ORIGINALS.get(address, {}).get(gmail_id) or await box.message(gmail_id)
            raw = gmail.build_reply(original, address, to, request.subject, request.body)
            sent = await box.send(raw, original.thread_id)
    except gmail.GmailError as error:
        raise gmail_failure(error) from error
    return {"sent": True, "gmail_id": sent.get("id"), "thread_id": sent.get("threadId")}
