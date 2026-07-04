"""Spam classification."""

# Standard Library
import re

from .models import (
    AddressList,
    Classification,
    EmailMessage,
    MailboxConfig,
    RuleType,
    SpamSettings,
)
from .spamassassin import SpamAssassinClient


class SpamClassifier:
    """Classify messages using mailbox policy, rules, and SpamAssassin."""

    def __init__(self, settings: SpamSettings) -> None:
        """Create classifier with global spam settings."""
        self.settings = settings
        self.spamassassin = SpamAssassinClient(settings.spamassassin)

    def classify(
        self,
        message: EmailMessage,
        mailbox: MailboxConfig,
    ) -> Classification:
        """Classify a full normalized email message."""
        local_classification = self.classify_local(
            message,
            mailbox,
            include_body_rules=True,
        )
        if _is_decisive(local_classification):
            return local_classification

        score = local_classification.score
        reasons = list(local_classification.reasons)

        spamassassin_result = self.spamassassin.check(message)
        if spamassassin_result.available:
            reasons.append(
                f"spamassassin:{spamassassin_result.score:.2f}/{spamassassin_result.required_score:.2f}"
            )
            threshold = (
                self.settings.spamassassin.required_score
                if self.settings.spamassassin.required_score is not None
                else spamassassin_result.required_score
            )
            if spamassassin_result.is_spam or spamassassin_result.score >= threshold:
                score += self.settings.min_score
        elif self.settings.spamassassin.enabled:
            reasons.append("spamassassin:unavailable")

        return Classification(
            is_spam=score >= self.settings.min_score,
            score=score,
            reasons=reasons,
        )

    def classify_local(
        self,
        message: EmailMessage,
        mailbox: MailboxConfig,
        *,
        include_body_rules: bool,
    ) -> Classification:
        """Classify a message using only local policy and configured rules."""
        if _address_matches(message.sender, mailbox.whitelist):
            return Classification(is_spam=False, score=0.0, reasons=["whitelist"])

        if _address_matches(message.sender, mailbox.blacklist):
            return Classification(
                is_spam=True,
                score=self.settings.min_score,
                reasons=["blacklist"],
            )

        score = 0.0
        reasons = []

        for rule in mailbox.rules:
            if rule.type == RuleType.BODY and not include_body_rules:
                continue
            value = _message_value(
                message, rule.type, self.settings.rule_text_max_chars
            )
            if rule.pattern.search(value):
                score += rule.score
                reasons.append(f"rule:{rule.type.value}:{rule.pattern.pattern}")

        return Classification(
            is_spam=score >= self.settings.min_score,
            score=score,
            reasons=reasons,
        )

    def needs_full_message(self, mailbox: MailboxConfig) -> bool:
        """Return true when classification may need body or raw message content."""
        return self.settings.spamassassin.enabled or any(
            rule.type == RuleType.BODY for rule in mailbox.rules
        )


def _message_value(
    message: EmailMessage,
    rule_type: RuleType,
    max_chars: int,
) -> str:
    if rule_type == RuleType.SENDER:
        return message.sender[:max_chars]
    if rule_type == RuleType.SUBJECT:
        return message.subject[:max_chars]
    return message.body[:max_chars]


def _is_decisive(classification: Classification) -> bool:
    return classification.is_spam or classification.reasons == ["whitelist"]


def _address_matches(sender: str, address_list: AddressList) -> bool:
    normalized_sender = sender.lower()
    sender_email = _extract_email(normalized_sender)
    if (
        sender_email in address_list.senders
        or normalized_sender in address_list.senders
    ):
        return True
    sender_domain = (
        sender_email.rsplit("@", maxsplit=1)[-1] if "@" in sender_email else ""
    )
    return sender_domain in address_list.domains


def _extract_email(sender: str) -> str:
    match = re.search(r"[\w.+-]+@[\w.-]+", sender)
    if match:
        return match.group(0)
    return sender
