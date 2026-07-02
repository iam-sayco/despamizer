"""SpamAssassin spamd client."""

# Standard Library
from dataclasses import dataclass
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

        payload = message.raw or _build_raw_message(message)
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

        payload = message.raw or _build_raw_message(message)
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


def _build_raw_message(message: EmailMessage) -> bytes:
    return (
        f"Message-ID: {message.message_id}\r\n"
        f"From: {message.sender}\r\n"
        f"Subject: {message.subject}\r\n"
        "\r\n"
        f"{message.body}"
    ).encode("utf-8", errors="replace")
