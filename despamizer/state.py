"""SQLite-backed worker state."""

# Standard Library
from dataclasses import dataclass
import hashlib
from pathlib import Path
import time

# Third Party
from sqlmodel import Field, Session, SQLModel, create_engine, select

from .models import EmailMessage, StateSettings

MAX_STORED_TEXT_CHARS = 1000


@dataclass(frozen=True)
class MessageFingerprint:
    """Stable message identity used by local state."""

    value: str
    message_id: str


class MessageState(SQLModel, table=True):
    """Persisted state for one mailbox message fingerprint."""

    mailbox: str = Field(primary_key=True)
    fingerprint: str = Field(primary_key=True)
    message_id: str
    sender: str
    subject: str
    status: str
    learned_as: str | None = None
    reason: str
    first_seen_at: int
    updated_at: int
    expires_at: int = Field(index=True)


class WorkerState:
    """Stores bounded message state used for feedback loops."""

    def __init__(self, settings: StateSettings) -> None:
        """Create state store and schema when missing."""
        self.settings = settings
        self.path = Path(settings.path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(f"sqlite:///{self.path}")
        SQLModel.metadata.create_all(self.engine)

    def has_ham_override(self, mailbox: str, message: EmailMessage) -> bool:
        """Return true when user already rescued this message from spam."""
        return self._has_status(mailbox, message, "rescued_ham")

    def was_moved_to_spam(self, mailbox: str, message: EmailMessage) -> bool:
        """Return true when despamizer previously moved this message to spam."""
        return self._has_status(mailbox, message, "moved_to_spam")

    def was_learned_as_spam(self, mailbox: str, message: EmailMessage) -> bool:
        """Return true when manual spam feedback was already learned."""
        fingerprint = fingerprint_message(message)
        with Session(self.engine) as session:
            statement = select(MessageState).where(
                MessageState.mailbox == mailbox,
                MessageState.fingerprint == fingerprint.value,
                MessageState.learned_as == "spam",
                MessageState.expires_at > int(time.time()),
            )
            return session.exec(statement).first() is not None

    def record_moved_to_spam(
        self,
        mailbox: str,
        message: EmailMessage,
        reason: str,
    ) -> None:
        """Record that despamizer moved a message to spam."""
        self._upsert(mailbox, message, "moved_to_spam", None, reason)

    def record_rescued_ham(self, mailbox: str, message: EmailMessage) -> None:
        """Record that user rescued a message from spam."""
        self._upsert(mailbox, message, "rescued_ham", "ham", "rescued_from_spam")

    def record_manual_spam(self, mailbox: str, message: EmailMessage) -> None:
        """Record that user manually placed a message in spam."""
        self._upsert(mailbox, message, "manual_spam", "spam", "manual_spam")

    def delete_messages(self, mailbox: str, messages: list[EmailMessage]) -> int:
        """Delete local state rows for permanently deleted remote messages."""
        deleted_count = 0
        with Session(self.engine) as session:
            for message in messages:
                fingerprint = fingerprint_message(message)
                rows = []
                row = session.get(MessageState, (mailbox, fingerprint.value))
                if row is not None:
                    rows.append(row)
                if fingerprint.message_id:
                    rows.extend(
                        session.exec(
                            select(MessageState).where(
                                MessageState.mailbox == mailbox,
                                MessageState.message_id == fingerprint.message_id,
                            )
                        ).all()
                    )
                seen_keys = set()
                for row in rows:
                    key = (row.mailbox, row.fingerprint)
                    if key in seen_keys:
                        continue
                    seen_keys.add(key)
                    session.delete(row)
                    deleted_count += 1
            session.commit()
        return deleted_count

    def cleanup(self) -> int:
        """Delete expired state rows and return deletion count."""
        now = int(time.time())
        with Session(self.engine) as session:
            expired_rows = session.exec(
                select(MessageState).where(MessageState.expires_at <= now)
            ).all()
            for row in expired_rows:
                session.delete(row)
            session.commit()
            return len(expired_rows)

    def _has_status(self, mailbox: str, message: EmailMessage, status: str) -> bool:
        fingerprint = fingerprint_message(message)
        with Session(self.engine) as session:
            statement = select(MessageState).where(
                MessageState.mailbox == mailbox,
                MessageState.fingerprint == fingerprint.value,
                MessageState.status == status,
                MessageState.expires_at > int(time.time()),
            )
            return session.exec(statement).first() is not None

    def _upsert(
        self,
        mailbox: str,
        message: EmailMessage,
        status: str,
        learned_as: str | None,
        reason: str,
    ) -> None:
        now = int(time.time())
        expires_at = now + self.settings.retention_days * 24 * 60 * 60
        fingerprint = fingerprint_message(message)
        with Session(self.engine) as session:
            row = session.get(MessageState, (mailbox, fingerprint.value))
            if row is None:
                row = MessageState(
                    mailbox=mailbox,
                    fingerprint=fingerprint.value,
                    message_id=_truncate_text(fingerprint.message_id),
                    sender=_truncate_text(message.sender),
                    subject=_truncate_text(message.subject),
                    status=status,
                    learned_as=learned_as,
                    reason=_truncate_text(reason),
                    first_seen_at=now,
                    updated_at=now,
                    expires_at=expires_at,
                )
            else:
                row.message_id = _truncate_text(fingerprint.message_id)
                row.sender = _truncate_text(message.sender)
                row.subject = _truncate_text(message.subject)
                row.status = status
                row.learned_as = learned_as
                row.reason = _truncate_text(reason)
                row.updated_at = now
                row.expires_at = expires_at
            session.add(row)
            session.commit()


def fingerprint_message(message: EmailMessage) -> MessageFingerprint:
    """Build stable fingerprint without storing full message body."""
    message_id = message.message_id.strip().lower()
    if message_id:
        return MessageFingerprint(
            value=hashlib.sha256(f"message-id:{message_id}".encode()).hexdigest(),
            message_id=message_id,
        )
    fallback = "\n".join(
        [
            message.sender.lower(),
            message.subject.lower(),
            hashlib.sha256(message.raw or message.body.encode()).hexdigest(),
        ]
    )
    return MessageFingerprint(
        value=hashlib.sha256(fallback.encode()).hexdigest(),
        message_id="",
    )


def _truncate_text(value: str) -> str:
    if len(value) <= MAX_STORED_TEXT_CHARS:
        return value
    return value[:MAX_STORED_TEXT_CHARS]
