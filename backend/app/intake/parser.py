"""Inbound email parsing (App Flow §11 steps 3–4).

Pure: raw RFC-822 bytes in, a `ParsedEmail` out. `problem` is the malformed
verdict — a non-None value is what routes the message to the manual review
queue instead of the ticket-creation path, so nothing is ever dropped silently.

stdlib `email` does the whole job; there is no parsing dependency.
"""

import re
from dataclasses import dataclass, field
from email import message_from_bytes
from email.message import EmailMessage
from email.policy import default as default_policy
from email.utils import parseaddr

# The acknowledgment subject carries `[AGT-123]` — same ref format the UI shows
# (`TicketOut.ref`), which is what makes a customer's reply matchable.
DISPLAY_ID_RE = re.compile(r"\[AGT-(\d+)\]", re.I)
_SUBJECT_PREFIX_RE = re.compile(r"^\s*((re|fw|fwd|aw|sv)\s*(\[\d+\])?\s*:\s*)+", re.I)
_TAG_RE = re.compile(r"<[^>]+>")
_MESSAGE_ID_RE = re.compile(r"<[^<>@\s]+@[^<>\s]+>")
# Where the customer's own words stop and the quoted history starts.
_QUOTE_RE = re.compile(
    r"^(>|On .{0,200}\bwrote:|-{2,}\s*Original Message|_{5,}|Sent from my )", re.M
)


@dataclass
class ParsedEmail:
    sender_email: str = ""
    sender_name: str = ""
    subject: str = ""
    body: str = ""
    message_id: str | None = None
    references: list[str] = field(default_factory=list)
    attachments: list[tuple[str, str, bytes]] = field(default_factory=list)
    problem: str | None = None
    """Non-None ⇒ malformed; route to manual review (§11 step 4)."""


def normalise_subject(subject: str) -> str:
    """`Re: Fwd: Printer jammed` → `printer jammed`, for the sender+subject
    fallback match. Also drops the `[AGT-…]` tag so a tagged and an untagged
    copy of the same thread still compare equal."""
    return DISPLAY_ID_RE.sub("", _SUBJECT_PREFIX_RE.sub("", subject)).strip().lower()


def display_id_in(subject: str) -> int | None:
    match = DISPLAY_ID_RE.search(subject or "")
    return int(match.group(1)) if match else None


def strip_quoted(body: str) -> str:
    """Keep only the new text. A reply whose entire content is quoted history
    keeps the history — better a noisy comment than an empty one."""
    match = _QUOTE_RE.search(body)
    trimmed = body[: match.start()].strip() if match else body.strip()
    return trimmed or body.strip()


def _text_of(message: EmailMessage) -> str:
    try:
        part = message.get_body(preferencelist=("plain", "html"))
        if part is None:
            return ""
        text = part.get_content()
    except (LookupError, ValueError, TypeError):
        # Unknown charset or a broken Content-Type — treated as malformed below
        return ""
    if part.get_content_subtype() == "html":
        text = _TAG_RE.sub(" ", text)
    return text.replace("\x00", "").strip()


def _attachments_of(message: EmailMessage) -> list[tuple[str, str, bytes]]:
    found = []
    for part in message.iter_attachments():
        content = part.get_payload(decode=True)
        if not content:
            continue
        found.append(
            (
                part.get_filename() or "attachment",
                part.get_content_type() or "application/octet-stream",
                content,
            )
        )
    return found


def parse(raw: bytes) -> ParsedEmail:
    try:
        message = message_from_bytes(raw, policy=default_policy)
    except Exception as exc:  # noqa: BLE001 — any parse failure is "malformed"
        return ParsedEmail(problem=f"unreadable message: {exc}")

    name, address = parseaddr(str(message.get("From", "")))
    subject = str(message.get("Subject", "")).strip()
    body = _text_of(message)
    # Angle brackets kept, so these compare directly against the stored
    # `tickets.source_email_message_id`.
    references = [
        ref
        for header in ("In-Reply-To", "References")
        for ref in _MESSAGE_ID_RE.findall(str(message.get(header, "")))
    ]

    parsed = ParsedEmail(
        sender_email=address.strip().lower(),
        sender_name=name.strip() or address.split("@")[0],
        subject=subject,
        body=strip_quoted(body),
        message_id=(str(message.get("Message-ID", "")).strip() or None),
        references=references,
        attachments=_attachments_of(message),
    )
    if "@" not in parsed.sender_email:
        parsed.problem = "no usable sender address"
    elif not parsed.body:
        parsed.problem = "empty or unreadable body"
    return parsed
