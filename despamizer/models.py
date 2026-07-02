"""Domain models for despamizer."""

# Standard Library
from dataclasses import dataclass, field
from enum import StrEnum
import re
from typing import Pattern


class RuleType(StrEnum):
    """Supported custom filtering rule types."""

    SENDER = "sender"
    SUBJECT = "subject"
    BODY = "body"


@dataclass(frozen=True)
class FilterRule:
    """A single spam scoring rule."""

    type: RuleType
    pattern: Pattern[str]
    score: float = 10.0


@dataclass(frozen=True)
class AddressList:
    """Sender and domain list used for mailbox allow/block decisions."""

    senders: list[str] = field(default_factory=list)
    domains: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SpamAssassinSettings:
    """SpamAssassin spamd connection settings."""

    enabled: bool = True
    host: str = "spamassassin"
    port: int = 783
    timeout_seconds: int = 15
    required_score: float | None = None


@dataclass(frozen=True)
class LearningSettings:
    """Settings for feedback-based SpamAssassin learning."""

    enabled: bool = True
    learn_rescued_ham: bool = True
    learn_manual_spam: bool = True
    scan_spam_folder: bool = True
    max_spam_folder_messages_per_run: int = 100


@dataclass(frozen=True)
class StateSettings:
    """Settings for local worker state."""

    path: str = "/app/state/despamizer.sqlite"
    retention_days: int = 365


@dataclass(frozen=True)
class SpamSettings:
    """Global spam scoring settings."""

    min_score: float = 5.0
    spamassassin: SpamAssassinSettings = field(default_factory=SpamAssassinSettings)
    learning: LearningSettings = field(default_factory=LearningSettings)


@dataclass(frozen=True)
class MailboxConfig:
    """Configuration for one IMAP mailbox."""

    name: str
    host: str
    port: int
    username: str
    password: str
    inbox_folder: str
    spam_folder: str
    whitelist: AddressList = field(default_factory=AddressList)
    blacklist: AddressList = field(default_factory=AddressList)
    rules: list[FilterRule] = field(default_factory=list)


@dataclass(frozen=True)
class AppConfig:
    """Application configuration."""

    poll_interval_seconds: int
    dry_run: bool
    log_retention_days: int
    state: StateSettings
    spam: SpamSettings
    mailboxes: list[MailboxConfig]


@dataclass(frozen=True)
class EmailMessage:
    """Normalized email data used by classifiers."""

    uid: str
    message_id: str
    sender: str
    subject: str
    body: str
    raw: bytes = b""


@dataclass(frozen=True)
class Classification:
    """Spam classification result."""

    is_spam: bool
    score: float
    reasons: list[str]


def compile_rule_pattern(pattern: str) -> Pattern[str]:
    """Compile a case-insensitive regex rule pattern."""
    return re.compile(pattern, re.IGNORECASE | re.MULTILINE)
