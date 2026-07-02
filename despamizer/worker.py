"""Worker orchestration for despamizer."""

# Standard Library
import time
import traceback
from typing import Callable

from .classifier import SpamClassifier
from .logger import cleanup_logs, log_message
from .models import AppConfig, EmailMessage, MailboxConfig
from .imap_client import ImapMailboxClient
from .state import WorkerState

ClientFactory = Callable[[MailboxConfig], ImapMailboxClient]


class DespamizerWorker:
    """Poll configured mailboxes and move spam messages."""

    def __init__(
        self,
        config: AppConfig,
        client_factory: ClientFactory = ImapMailboxClient,
    ) -> None:
        """Create worker."""
        self.config = config
        self.client_factory = client_factory
        self.classifier = SpamClassifier(config.spam)
        self.state = WorkerState(config.state)

    def run_once(self) -> None:
        """Process all configured mailboxes once."""
        for mailbox in self.config.mailboxes:
            self._process_mailbox(mailbox)
        deleted_rows = self.state.cleanup()
        if deleted_rows:
            log_message(f"[INFO] Deleted {deleted_rows} expired state rows")
        cleanup_logs(self.config.log_retention_days)

    def run_forever(self) -> None:
        """Run worker loop forever."""
        while True:
            self.run_once()
            time.sleep(self.config.poll_interval_seconds)

    def _process_mailbox(self, mailbox: MailboxConfig) -> None:
        log_message(f"[START] Scanning mailbox: {mailbox.name}")
        spam_count = 0
        moved_count = 0
        would_move_count = 0
        skipped_count = 0
        try:
            with self.client_factory(mailbox) as client:
                messages = client.iter_inbox_messages()
                log_message(
                    f"[INFO] {mailbox.name}: fetched {len(messages)} inbox messages"
                )
                for message in messages:
                    if self._handle_rescued_ham(mailbox, message):
                        skipped_count += 1
                        continue
                    classification = self.classifier.classify(message, mailbox)
                    if not classification.is_spam:
                        continue
                    spam_count += 1
                    reason = ", ".join(classification.reasons) or "no reason"
                    log_message(
                        f"[SPAM] {mailbox.name}: uid={message.uid} "
                        f"score={classification.score:.2f} reasons={reason}"
                    )
                    if self.config.dry_run:
                        log_message(
                            f"[DRY-RUN] {mailbox.name}: would move uid={message.uid} "
                            f"to {mailbox.spam_folder}"
                        )
                        would_move_count += 1
                        continue
                    client.move_to_spam(message.uid)
                    self.state.record_moved_to_spam(mailbox.name, message, reason)
                    moved_count += 1
                    log_message(
                        f"[MOVED] {mailbox.name}: uid={message.uid} -> {mailbox.spam_folder}"
                    )
                if not self.config.dry_run:
                    self._learn_manual_spam(mailbox, client)
                log_message(
                    f"[SUMMARY] {mailbox.name}: scanned={len(messages)} "
                    f"spam={spam_count} moved={moved_count} "
                    f"would_move={would_move_count} skipped={skipped_count}"
                )
        except Exception as exc:
            log_message(
                f"[ERROR] {mailbox.name}: {exc}\n{traceback.format_exc()}"
            )

    def _handle_rescued_ham(
        self,
        mailbox: MailboxConfig,
        message: EmailMessage,
    ) -> bool:
        if not self.config.spam.learning.enabled:
            return False
        if not self.config.spam.learning.learn_rescued_ham:
            return self.state.has_ham_override(mailbox.name, message)
        if self.state.has_ham_override(mailbox.name, message):
            return True
        if not self.state.was_moved_to_spam(mailbox.name, message):
            return False
        if self.config.dry_run:
            log_message(
                f"[DRY-RUN] {mailbox.name}: would learn uid={message.uid} as ham"
            )
            return True

        learned = self.classifier.spamassassin.learn(message, "ham")
        self.state.record_rescued_ham(mailbox.name, message)
        log_message(
            f"[LEARN] {mailbox.name}: uid={message.uid} rescued ham "
            f"learned={learned}"
        )
        return True

    def _learn_manual_spam(
        self,
        mailbox: MailboxConfig,
        client: ImapMailboxClient,
    ) -> None:
        learning = self.config.spam.learning
        if not learning.enabled or not learning.learn_manual_spam:
            return
        if not learning.scan_spam_folder:
            return

        spam_messages = client.iter_spam_messages(learning.max_spam_folder_messages_per_run)
        learned_count = 0
        skipped_count = 0
        failed_count = 0
        for message in spam_messages:
            if self.state.was_moved_to_spam(mailbox.name, message):
                skipped_count += 1
                continue
            if self.state.was_learned_as_spam(mailbox.name, message):
                skipped_count += 1
                continue
            learned = self.classifier.spamassassin.learn(message, "spam")
            if not learned:
                failed_count += 1
                continue
            self.state.record_manual_spam(mailbox.name, message)
            learned_count += 1
        if spam_messages:
            log_message(
                f"[LEARN] {mailbox.name}: manual spam scanned={len(spam_messages)} "
                f"learned={learned_count} skipped={skipped_count} failed={failed_count}"
            )
