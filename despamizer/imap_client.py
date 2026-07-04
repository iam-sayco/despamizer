"""IMAP client wrapper."""

# Standard Library
import datetime

from .models import EmailMessage, MailboxConfig


class ImapMailboxClient:
    """Small wrapper around imap-tools to keep IMAP operations constrained."""

    def __init__(self, config: MailboxConfig) -> None:
        """Create IMAP client for a single mailbox."""
        from imap_tools import MailBox

        self.config = config
        self._mailbox = MailBox(config.host, config.port)

    def __enter__(self) -> "ImapMailboxClient":
        """Login and select inbox folder."""
        self._mailbox.login(self.config.username, self.config.password)
        self._mailbox.folder.set(self.config.inbox_folder)
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        """Logout from IMAP mailbox."""
        self._mailbox.logout()

    def iter_inbox_messages(self) -> list[EmailMessage]:
        """Fetch inbox message headers without marking messages as seen."""
        self._mailbox.folder.set(self.config.inbox_folder)
        messages = []
        for message in self._mailbox.fetch(
            "ALL",
            mark_seen=False,
            headers_only=True,
            bulk=True,
        ):
            messages.append(_normalize_message(message, include_body=False))
        return messages

    def get_inbox_message(self, uid: str) -> EmailMessage:
        """Fetch one full inbox message by UID without marking it as seen."""
        _validate_uid(uid)
        self._mailbox.folder.set(self.config.inbox_folder)
        message = next(
            self._mailbox.fetch(f"UID {uid}", mark_seen=False, bulk=False),
            None,
        )
        if message is None:
            raise ValueError(f"Message not found: uid={uid}")
        return _normalize_message(message, include_body=True)

    def list_folders(self) -> list[str]:
        """Return IMAP folder names."""
        return [folder.name for folder in self._mailbox.folder.list()]

    def iter_spam_messages(self, limit: int) -> list[EmailMessage]:
        """Fetch messages from configured spam folder without marking them as seen."""
        self._mailbox.folder.set(self.config.spam_folder)
        messages = []
        for index, message in enumerate(
            self._mailbox.fetch("ALL", mark_seen=False, bulk=False),
            start=1,
        ):
            if index > limit:
                break
            messages.append(_normalize_message(message, include_body=True))
        return messages

    def delete_old_spam_messages(self, retention_days: int) -> list[EmailMessage]:
        """Permanently delete spam messages older than retention days."""
        self._mailbox.folder.set(self.config.spam_folder)
        cutoff = datetime.datetime.now(datetime.UTC) - datetime.timedelta(
            days=retention_days
        )
        search_criteria = f"BEFORE {cutoff.strftime('%d-%b-%Y')}"
        deleted_messages = []
        for message in self._mailbox.fetch(
            search_criteria,
            mark_seen=False,
            headers_only=True,
            bulk=True,
        ):
            if not _is_older_than(message.date, cutoff):
                continue
            deleted_messages.append(_normalize_message(message, include_body=False))

        if deleted_messages:
            deleted_uids = [message.uid for message in deleted_messages]
            for uid in deleted_uids:
                _validate_uid(uid)
            self._mailbox.delete(deleted_uids)
            self._mailbox.expunge()
        return deleted_messages

    def move_to_spam(self, uid: str) -> None:
        """Move one message to the configured spam folder."""
        _validate_uid(uid)
        self._mailbox.move(uid, self.config.spam_folder)


def _normalize_message(message: object, *, include_body: bool) -> EmailMessage:
    body = ""
    if include_body:
        body = "\n".join(part for part in [message.text, message.html] if part)
    raw = b""
    message_id = ""
    message_obj = message.obj
    if message_obj is not None:
        if include_body:
            raw = message_obj.as_bytes()
        message_id = message_obj.get("Message-ID", "")
    return EmailMessage(
        uid=str(message.uid),
        message_id=message_id,
        sender=message.from_ or "",
        subject=message.subject or "",
        body=body,
        raw=raw,
        received_at=message.date,
    )


def _is_older_than(
    message_date: datetime.datetime | None,
    cutoff: datetime.datetime,
) -> bool:
    if message_date is None:
        return False
    if message_date.tzinfo is None:
        message_date = message_date.replace(tzinfo=datetime.UTC)
    return message_date <= cutoff


def _validate_uid(uid: str) -> None:
    if not uid.isdigit():
        raise ValueError("IMAP UID must be numeric")
