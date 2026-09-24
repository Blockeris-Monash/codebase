"""The signed-in person's Gmail: read new mail into the pipeline, send a reply (task 2).

The browser holds the Google access token Supabase handed back at sign-in and sends
it with each request. This server uses it for that one request and never stores it:
no token in the database, the logs or the repo, so there is nothing here to leak.
The token lasts about an hour; after that the page asks for a new sign-in.

Scopes asked for at sign-in: gmail.readonly to read, gmail.send to reply. Neither
can delete or change mail.
"""
from __future__ import annotations

import base64
import html
import re
from dataclasses import dataclass, field
from email.message import EmailMessage
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

from backend.contracts import DocumentRoleType
from backend.read.documents import document_title
from backend.read.labels import detect_doc_type

API = "https://gmail.googleapis.com/gmail/v1/users/me"
PREFIX = "gmail_"
# Newest first, and few: every new email costs a model call or two, and 11 to 25 s.
RECENT = "in:inbox newer_than:14d"
MAX_MESSAGES = 20
# Tests put a fake Gmail here; in service it stays None and httpx goes to Google.
TRANSPORT: Optional[httpx.AsyncBaseTransport] = None


class GmailError(Exception):
    """Gmail refused or could not be reached. `status` is Google's HTTP status."""

    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status = status


def mailbox_id(gmail_id: str) -> str:
    """The id the pipeline and the page use. Prefixed so it can never collide with a
    demo email_NNN, whose marks the same page keeps."""
    return PREFIX + gmail_id


def gmail_id_of(email_id: str) -> Optional[str]:
    return email_id[len(PREFIX):] if email_id.startswith(PREFIX) else None


# ------------------------------------------------------------- parsing

@dataclass
class Attachment:
    filename: str
    attachment_id: Optional[str] = None
    data: Optional[bytes] = None  # small parts come inline, large ones by attachment_id


@dataclass
class Message:
    gmail_id: str
    thread_id: str
    sender: str
    to: str
    subject: str
    message_id: str  # the RFC 822 Message-ID, which a reply must quote to thread
    date: str
    body: str
    attachments: List[Attachment] = field(default_factory=list)


def b64(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def html_to_text(markup: str) -> str:
    markup = re.sub(r"(?is)<(script|style).*?</\1>", "", markup)
    markup = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</tr>", "\n", markup)
    return html.unescape(re.sub(r"<[^>]+>", "", markup)).strip()


def walk(part: Dict[str, Any]):
    yield part
    for child in part.get("parts") or []:
        yield from walk(child)


def parse_message(raw: Dict[str, Any]) -> Message:
    """One Gmail `format=full` message as the fields the pipeline and a reply need."""
    payload = raw.get("payload") or {}
    headers = {h["name"].lower(): h["value"] for h in payload.get("headers") or []}

    plain, markup, attachments = [], [], []
    for part in walk(payload):
        body, name = part.get("body") or {}, part.get("filename") or ""
        if name:
            inline = b64(body["data"]) if body.get("data") else None
            attachments.append(Attachment(name, body.get("attachmentId"), inline))
        elif part.get("mimeType") == "text/plain" and body.get("data"):
            plain.append(b64(body["data"]).decode("utf-8", errors="replace"))
        elif part.get("mimeType") == "text/html" and body.get("data"):
            markup.append(b64(body["data"]).decode("utf-8", errors="replace"))

    text = "\n".join(plain) if plain else html_to_text("\n".join(markup))
    return Message(
        gmail_id=raw["id"],
        thread_id=raw.get("threadId", ""),
        sender=headers.get("from", ""),
        to=headers.get("to", ""),
        subject=headers.get("subject", ""),
        message_id=headers.get("message-id", ""),
        date=headers.get("date", ""),
        body=text.strip(),
        attachments=attachments,
    )


# ------------------------------------------------------------ attachments

NAME_HINTS = [
    (re.compile(r"shipping.?instruction|(^|[^a-z])si([^a-z]|$)", re.I), DocumentRoleType.Si),
    (re.compile(r"bill.?of.?lading|(^|[^a-z])b/?l([^a-z]|$)", re.I), DocumentRoleType.Bl),
]


def role_of(path: Path, original_name: str) -> Optional[str]:
    """SI or BL. The document's own title first, since that is what the comparator
    trusts; the sender's file name only when the title says neither."""
    role = detect_doc_type(document_title(path) or "")
    if role in (DocumentRoleType.Si, DocumentRoleType.Bl):
        return role
    stem = Path(original_name).stem
    for pattern, hinted in NAME_HINTS:
        if pattern.search(stem):
            return hinted
    return None


SAFE_SUFFIX = re.compile(r"^\.[a-z0-9]{1,5}$")


def save_attachments(email_id: str, files: List[tuple[str, bytes]], folder: Path) -> List[str]:
    """Write each attachment where /process-email can read it, named the way the
    pipeline pairs documents: <email_id>_SI.pdf, <email_id>_BL.pdf, then _SI_2 for a
    second shipment. A file that is neither keeps a neutral name and is skipped by
    the pairing. The sender's file name is never used as a path."""
    folder.mkdir(parents=True, exist_ok=True)
    saved, seen = [], {DocumentRoleType.Si: 0, DocumentRoleType.Bl: 0}
    for n, (name, data) in enumerate(files, 1):
        suffix = Path(name).suffix.lower()
        suffix = suffix if SAFE_SUFFIX.match(suffix) else ".bin"
        probe = folder / f"{email_id}_file{n}{suffix}"
        probe.write_bytes(data)
        role = role_of(probe, name)
        if role is None:
            saved.append(str(probe))
            continue
        seen[role] += 1
        final = folder / f"{email_id}_{role}{'' if seen[role] == 1 else '_' + str(seen[role])}{suffix}"
        probe.replace(final)
        saved.append(str(final))
    return saved


# ----------------------------------------------------------------- reply

def reply_subject(subject: str) -> str:
    return subject if re.match(r"(?i)^\s*re:", subject) else f"Re: {subject}"


def build_reply(original: Message, sender: str, to: str, subject: str, body: str) -> str:
    """The reply as Gmail's `raw` (base64url RFC 822), threaded under the original.
    EmailMessage refuses a header with a line break, so a crafted address or subject
    cannot add headers of its own."""
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = to
    msg["Subject"] = reply_subject(subject or original.subject)
    if original.message_id:
        msg["In-Reply-To"] = original.message_id
        msg["References"] = original.message_id
    msg.set_content(body)
    return base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii")


# ---------------------------------------------------------------- client

class Gmail:
    """The few Gmail calls this app makes, as the person whose token it holds."""

    def __init__(self, token: str, transport: Optional[httpx.AsyncBaseTransport] = None):
        self.client = httpx.AsyncClient(base_url=API, transport=transport or TRANSPORT, timeout=30,
                                        headers={"Authorization": f"Bearer {token}"})

    async def __aenter__(self) -> "Gmail":
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.client.aclose()

    async def call(self, method: str, path: str, **kwargs: Any) -> Dict[str, Any]:
        try:
            response = await self.client.request(method, path, **kwargs)
        except httpx.HTTPError as error:
            raise GmailError(502, f"Gmail could not be reached: {error}") from error
        if response.status_code >= 400:
            try:
                detail = response.json().get("error", {}).get("message", "")
            except ValueError:
                detail = response.text[:200]
            raise GmailError(response.status_code, detail or f"Gmail answered {response.status_code}")
        return response.json()

    async def address(self) -> str:
        return (await self.call("GET", "/profile"))["emailAddress"]

    async def recent_ids(self) -> List[str]:
        found = await self.call("GET", "/messages", params={"q": RECENT, "maxResults": MAX_MESSAGES})
        return [m["id"] for m in found.get("messages") or []]

    async def message(self, gmail_id: str) -> Message:
        return parse_message(await self.call("GET", f"/messages/{gmail_id}", params={"format": "full"}))

    async def attachment_files(self, message: Message) -> List[tuple[str, bytes]]:
        files = []
        for att in message.attachments:
            data = att.data
            if data is None and att.attachment_id:
                got = await self.call("GET", f"/messages/{message.gmail_id}/attachments/{att.attachment_id}")
                data = b64(got.get("data", ""))
            files.append((att.filename, data or b""))
        return files

    async def send(self, raw: str, thread_id: str) -> Dict[str, Any]:
        body = {"raw": raw, **({"threadId": thread_id} if thread_id else {})}
        return await self.call("POST", "/messages/send", json=body)
