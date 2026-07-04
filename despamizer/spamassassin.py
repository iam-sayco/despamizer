"""SpamAssassin spamd client."""

# Standard Library
from dataclasses import dataclass
from email.message import EmailMessage as StdlibEmailMessage
from email.policy import SMTP
import re
import socket

from .logger import log_message
from .models import EmailMessage, SpamAssassinSettings


@dataclass(frozen=True)
class SpamAssassinResult:
    """Result returned by SpamAssassin."""

    available: bool
    is_spam: bool = False
    score: float = 0.0
    required_score: float = 5.0


class SpamAssassinClient:
    """Client for the SpamAssassin spamd CHECK protocol."""

    def __init__(self, settings: SpamAssassinSettings) -> None:
        """Create SpamAssassin client."""
        self.settings = settings

    def check(self, message: EmailMessage) -> SpamAssassinResult:
        """Check a message with spamd."""
        if not self.settings.enabled:
            return SpamAssassinResult(available=False)

        payload = _payload_for_spamd(message, self.settings.message_bytes_max)
        request = _build_request("CHECK", payload)
        try:
            response = self._send(request)
        except OSError as exc:
            log_message(f"[WARN] SpamAssassin unavailable: {exc}")
            return SpamAssassinResult(available=False)

        return _parse_response(response)

    def learn(self, message: EmailMessage, message_class: str) -> bool:
        """Tell SpamAssassin to learn a message as spam or ham."""
        if not self.settings.enabled:
            return False
        if message_class not in {"spam", "ham"}:
            raise ValueError("message_class must be spam or ham")

        payload = _payload_for_spamd(message, self.settings.message_bytes_max)
        request = _build_request(
            "TELL",
            payload,
            [
                f"Message-class: {message_class}",
                "Set: local",
            ],
        )
        try:
            response = self._send(request)
        except OSError as exc:
            log_message(f"[WARN] SpamAssassin learning unavailable: {exc}")
            return False
        return response.startswith("SPAMD/") and "EX_OK" in response.splitlines()[0]

    def _send(self, request: bytes) -> str:
        with socket.create_connection(
            (self.settings.host, self.settings.port),
            timeout=self.settings.timeout_seconds,
        ) as connection:
            connection.settimeout(self.settings.timeout_seconds)
            connection.sendall(request)
            return _read_response(connection)


def _read_response(connection: socket.socket) -> str:
    chunks = []
    while True:
        chunk = connection.recv(4096)
        if not chunk:
            break
        chunks.append(chunk)
    return b"".join(chunks).decode("utf-8", errors="replace")


def _parse_response(response: str) -> SpamAssassinResult:
    spam_match = re.search(
        r"Spam:\s+(True|False)\s*;\s*([-+]?\d+(?:\.\d+)?)\s*/\s*([-+]?\d+(?:\.\d+)?)",
        response,
        re.IGNORECASE,
    )
    if not spam_match:
        return SpamAssassinResult(available=False)
    is_spam = spam_match.group(1).lower() == "true"
    return SpamAssassinResult(
        available=True,
        is_spam=is_spam,
        score=float(spam_match.group(2)),
        required_score=float(spam_match.group(3)),
    )


def _build_request(command: str, payload: bytes, headers: list[str] | None = None) -> bytes:
    request_headers = [f"{command} SPAMC/1.5", f"Content-length: {len(payload)}"]
    if headers:
        request_headers.extend(headers)
    return ("\r\n".join(request_headers) + "\r\n\r\n").encode() + payload


def _payload_for_spamd(message: EmailMessage, max_bytes: int) -> bytes:
    payload = message.raw or _build_raw_message(message)
    if len(payload) <= max_bytes:
        return payload
    trimmed_payload = _trim_message_payload(payload, max_bytes)
    log_message(
        f"[WARN] SpamAssassin message trimmed: "
        f"bytes={len(payload)} sent={len(trimmed_payload)} max={max_bytes}"
    )
    return trimmed_payload


def _trim_message_payload(payload: bytes, max_bytes: int) -> bytes:
    header_separator = b"\r\n\r\n"
    separator_length = len(header_separator)
    header_end = payload.find(header_separator)
    if header_end < 0:
        header_separator = b"\n\n"
        separator_length = len(header_separator)
        header_end = payload.find(header_separator)
    if header_end < 0:
        return payload[:max_bytes]

    body_start = header_end + separator_length
    if body_start >= max_bytes:
        return payload[:max_bytes]
    body_bytes_max = max_bytes - body_start
    return payload[:body_start] + payload[body_start : body_start + body_bytes_max]


def _build_raw_message(message: EmailMessage) -> bytes:
    email_message = StdlibEmailMessage(policy=SMTP)
    if message.message_id.strip():
        email_message["Message-ID"] = _sanitize_header_value(message.message_id)
    email_message["From"] = _sanitize_header_value(message.sender)
    email_message["Subject"] = _sanitize_header_value(message.subject)
    email_message.set_content(message.body)
    return email_message.as_bytes()


def _sanitize_header_value(value: str) -> str:
    return " ".join(value.splitlines())
