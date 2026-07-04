from despamizer.classifier import SpamClassifier
from despamizer.models import (
    AddressList,
    EmailMessage,
    FilterRule,
    MailboxConfig,
    RuleType,
    SpamAssassinSettings,
    SpamSettings,
    compile_rule_pattern,
)
from despamizer.spamassassin import SpamAssassinResult


class FakeSpamAssassin:
    result = SpamAssassinResult(available=False)
    calls = 0

    def __init__(self, settings):
        self.settings = settings

    def check(self, message):
        self.__class__.calls += 1
        return self.result


def mailbox_with_rules(rules, whitelist=None, blacklist=None):
    return MailboxConfig(
        name="test",
        host="imap.example.com",
        port=993,
        username="user@example.com",
        password="secret",
        inbox_folder="INBOX",
        spam_folder="Junk",
        whitelist=whitelist or AddressList(),
        blacklist=blacklist or AddressList(),
        rules=rules,
    )


def test_classifier_marks_sender_rule_match_as_spam():
    classifier = SpamClassifier(
        SpamSettings(
            min_score=5,
            spamassassin=SpamAssassinSettings(enabled=False),
        )
    )
    message = EmailMessage(
        uid="1",
        message_id="<spam-1@example.com>",
        sender="promo@spam.example",
        subject="hello",
        body="normal body",
    )
    rules = [
        FilterRule(RuleType.SENDER, compile_rule_pattern("@spam\\.example$"), 10)
    ]

    result = classifier.classify(message, mailbox_with_rules(rules))

    assert result.is_spam is True
    assert result.score == 10
    assert result.reasons == ["rule:sender:@spam\\.example$"]


def test_classifier_ignores_non_matching_rules():
    classifier = SpamClassifier(
        SpamSettings(
            min_score=5,
            spamassassin=SpamAssassinSettings(enabled=False),
        )
    )
    message = EmailMessage(
        uid="1",
        message_id="<ham-1@example.com>",
        sender="friend@example.com",
        subject="hello",
        body="normal body",
    )
    rules = [
        FilterRule(RuleType.SUBJECT, compile_rule_pattern("free money"), 10)
    ]

    result = classifier.classify(message, mailbox_with_rules(rules))

    assert result.is_spam is False
    assert result.score == 0
    assert result.reasons == []


def test_classifier_accumulates_rule_scores():
    classifier = SpamClassifier(
        SpamSettings(
            min_score=10,
            spamassassin=SpamAssassinSettings(enabled=False),
        )
    )
    message = EmailMessage(
        uid="1",
        message_id="<mixed-1@example.com>",
        sender="friend@example.com",
        subject="crypto giveaway",
        body="unsubscribe here",
    )
    rules = [
        FilterRule(RuleType.SUBJECT, compile_rule_pattern("crypto"), 6),
        FilterRule(RuleType.BODY, compile_rule_pattern("unsubscribe"), 4),
    ]

    result = classifier.classify(message, mailbox_with_rules(rules))

    assert result.is_spam is True
    assert result.score == 10


def test_classifier_skips_spamassassin_when_local_rules_are_decisive(monkeypatch):
    monkeypatch.setattr("despamizer.classifier.SpamAssassinClient", FakeSpamAssassin)
    FakeSpamAssassin.calls = 0
    FakeSpamAssassin.result = SpamAssassinResult(
        available=True,
        is_spam=False,
        score=0.0,
        required_score=5.0,
    )
    classifier = SpamClassifier(
        SpamSettings(
            min_score=5,
            spamassassin=SpamAssassinSettings(enabled=True),
        )
    )
    message = EmailMessage(
        uid="1",
        message_id="<spam-1@example.com>",
        sender="promo@spam.example",
        subject="hello",
        body="normal body",
    )
    rules = [
        FilterRule(RuleType.SENDER, compile_rule_pattern("@spam\\.example$"), 5)
    ]

    result = classifier.classify(message, mailbox_with_rules(rules))

    assert result.is_spam is True
    assert result.score == 5
    assert result.reasons == ["rule:sender:@spam\\.example$"]
    assert FakeSpamAssassin.calls == 0


def test_classifier_whitelist_wins_over_blacklist_and_rules():
    classifier = SpamClassifier(
        SpamSettings(
            min_score=5,
            spamassassin=SpamAssassinSettings(enabled=False),
        )
    )
    message = EmailMessage(
        "1",
        "<friend-1@example.com>",
        "Friend <friend@example.com>",
        "crypto",
        "body",
    )
    mailbox = mailbox_with_rules(
        [FilterRule(RuleType.SUBJECT, compile_rule_pattern("crypto"), 10)],
        whitelist=AddressList(senders=["friend@example.com"]),
        blacklist=AddressList(domains=["example.com"]),
    )

    result = classifier.classify(message, mailbox)

    assert result.is_spam is False
    assert result.reasons == ["whitelist"]


def test_classifier_blacklist_marks_as_spam():
    classifier = SpamClassifier(
        SpamSettings(
            min_score=5,
            spamassassin=SpamAssassinSettings(enabled=False),
        )
    )
    message = EmailMessage(
        "1",
        "<blacklist-1@example.com>",
        "promo@spam.example",
        "hello",
        "body",
    )
    mailbox = mailbox_with_rules([], blacklist=AddressList(domains=["spam.example"]))

    result = classifier.classify(message, mailbox)

    assert result.is_spam is True
    assert result.reasons == ["blacklist"]


def test_classifier_uses_spamassassin_result(monkeypatch):
    monkeypatch.setattr("despamizer.classifier.SpamAssassinClient", FakeSpamAssassin)
    FakeSpamAssassin.result = SpamAssassinResult(
        available=True,
        is_spam=True,
        score=7.2,
        required_score=5.0,
    )
    classifier = SpamClassifier(
        SpamSettings(
            min_score=5,
            spamassassin=SpamAssassinSettings(enabled=True),
        )
    )
    message = EmailMessage(
        "1",
        "<sa-1@example.com>",
        "promo@example.com",
        "hello",
        "body",
    )

    result = classifier.classify(message, mailbox_with_rules([]))

    assert result.is_spam is True
    assert result.score == 5
    assert result.reasons == ["spamassassin:7.20/5.00"]
