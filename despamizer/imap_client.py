"""IMAP client wrapper."""

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
        """Fetch messages from configured inbox without marking them as seen."""
        self._mailbox.folder.set(self.config.inbox_folder)
        return self._fetch_messages()

    def list_folders(self) -> list[str]:
        """Return IMAP folder names."""
        return [folder.name for folder in self._mailbox.folder.list()]

    def iter_spam_messages(self, limit: int) -> list[EmailMessage]:
        """Fetch messages from configured spam folder without marking them as seen."""
        self._mailbox.folder.set(self.config.spam_folder)
        messages = []
        for index, message in enumerate(
            self._mailbox.fetch("ALL", mark_seen=False, bulk=True),
            start=1,
        ):
            if index > limit:
                break
            messages.append(_normalize_message(message))
        return messages

    def _fetch_messages(self) -> list[EmailMessage]:
        messages = []
        for message in self._mailbox.fetch("ALL", mark_seen=False, bulk=True):
            messages.append(_normalize_message(message))
        return messages

    def move_to_spam(self, uid: str) -> None:
        """Move one message to the configured spam folder."""
        self._mailbox.move(uid, self.config.spam_folder)


def _normalize_message(message: object) -> EmailMessage:
    body = "\n".join(part for part in [message.text, message.html] if part)
    raw = b""
    message_id = ""
    message_obj = message.obj
    if message_obj is not None:
        raw = message_obj.as_bytes()
        message_id = message_obj.get("Message-ID", "")
    return EmailMessage(
        uid=str(message.uid),
        message_id=message_id,
        sender=message.from_ or "",
        subject=message.subject or "",
        body=body,
        raw=raw,
    )
