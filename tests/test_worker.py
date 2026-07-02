from despamizer.models import (
    AppConfig,
    EmailMessage,
    FilterRule,
    MailboxConfig,
    SpamSettings,
    SpamAssassinSettings,
    StateSettings,
    RuleType,
    compile_rule_pattern,
)
from despamizer.worker import DespamizerWorker


class FakeClient:
    moved = []
    messages = []
    spam_messages = []

    def __init__(self, config):
        self.config = config

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return None

    def iter_inbox_messages(self):
        return self.messages

    def iter_spam_messages(self, limit):
        return self.spam_messages[:limit]

    def move_to_spam(self, uid):
        self.moved.append((self.config.name, uid))


def build_config(tmp_path, dry_run=False):
    mailbox = MailboxConfig(
        name="test",
        host="imap.example.com",
        port=993,
        username="user@example.com",
        password="secret",
        inbox_folder="INBOX",
        spam_folder="Junk",
        rules=[
            FilterRule(RuleType.SENDER, compile_rule_pattern("@spam\\.example$"), 10)
        ],
    )
    return AppConfig(
        poll_interval_seconds=60,
        dry_run=dry_run,
        log_retention_days=30,
        state=StateSettings(path=str(tmp_path / "state.sqlite"), retention_days=365),
        spam=SpamSettings(
            min_score=5,
            spamassassin=SpamAssassinSettings(enabled=False),
        ),
        mailboxes=[mailbox],
    )


def test_worker_moves_only_spam_messages(monkeypatch, tmp_path):
    FakeClient.moved = []
    FakeClient.spam_messages = []
    FakeClient.messages = [
        EmailMessage("1", "<spam-1@example.com>", "promo@spam.example", "hello", "body"),
        EmailMessage("2", "<ham-1@example.com>", "friend@example.com", "hello", "body"),
    ]
    monkeypatch.setattr("despamizer.worker.cleanup_logs", lambda days: None)
    monkeypatch.setattr("despamizer.worker.log_message", lambda message: None)

    worker = DespamizerWorker(build_config(tmp_path), FakeClient)
    worker.run_once()

    assert FakeClient.moved == [("test", "1")]


def test_worker_dry_run_does_not_move_messages(monkeypatch, tmp_path):
    FakeClient.moved = []
    FakeClient.spam_messages = []
    FakeClient.messages = [
        EmailMessage("1", "<spam-1@example.com>", "promo@spam.example", "hello", "body"),
    ]
    monkeypatch.setattr("despamizer.worker.cleanup_logs", lambda days: None)
    logs = []
    monkeypatch.setattr("despamizer.worker.log_message", logs.append)

    worker = DespamizerWorker(build_config(tmp_path, dry_run=True), FakeClient)
    worker.run_once()

    assert FakeClient.moved == []
    assert any(
        "[SUMMARY] test: scanned=1 spam=1 moved=0 would_move=1 skipped=0" in message
        for message in logs
    )


def test_worker_continues_when_mailbox_fails(monkeypatch, tmp_path):
    class FailingClient(FakeClient):
        def __enter__(self):
            raise RuntimeError("connection failed")

    monkeypatch.setattr("despamizer.worker.cleanup_logs", lambda days: None)
    logs = []
    monkeypatch.setattr("despamizer.worker.log_message", logs.append)

    worker = DespamizerWorker(build_config(tmp_path), FailingClient)
    worker.run_once()

    assert any("[ERROR] test: connection failed" in message for message in logs)


def test_worker_learns_rescued_ham_and_skips_move(monkeypatch, tmp_path):
    FakeClient.moved = []
    FakeClient.spam_messages = []
    rescued_message = EmailMessage(
        "1",
        "<rescued@example.com>",
        "promo@spam.example",
        "hello",
        "body",
    )
    FakeClient.messages = [rescued_message]
    monkeypatch.setattr("despamizer.worker.cleanup_logs", lambda days: None)
    monkeypatch.setattr("despamizer.worker.log_message", lambda message: None)

    worker = DespamizerWorker(build_config(tmp_path), FakeClient)
    worker.state.record_moved_to_spam("test", rescued_message, "test")
    learned = []
    worker.classifier.spamassassin.learn = lambda message, message_class: learned.append(message_class) or True

    worker.run_once()

    assert learned == ["ham"]
    assert FakeClient.moved == []


def test_worker_learns_manual_spam_once(monkeypatch, tmp_path):
    FakeClient.moved = []
    FakeClient.messages = []
    FakeClient.spam_messages = [
        EmailMessage("10", "<manual-spam@example.com>", "bad@example.net", "spam", "body")
    ]
    monkeypatch.setattr("despamizer.worker.cleanup_logs", lambda days: None)
    logs = []
    monkeypatch.setattr("despamizer.worker.log_message", logs.append)

    worker = DespamizerWorker(build_config(tmp_path), FakeClient)
    learned = []
    worker.classifier.spamassassin.learn = lambda message, message_class: learned.append(message_class) or True

    worker.run_once()
    worker.run_once()

    assert learned == ["spam"]
    assert any(
        "[LEARN] test: manual spam scanned=1 learned=1 skipped=0 failed=0" in message
        for message in logs
    )
    assert any(
        "[LEARN] test: manual spam scanned=1 learned=0 skipped=1 failed=0" in message
        for message in logs
    )


def test_worker_dry_run_does_not_learn_manual_spam(monkeypatch, tmp_path):
    FakeClient.moved = []
    FakeClient.messages = []
    FakeClient.spam_messages = [
        EmailMessage("10", "<manual-spam@example.com>", "bad@example.net", "spam", "body")
    ]
    monkeypatch.setattr("despamizer.worker.cleanup_logs", lambda days: None)
    monkeypatch.setattr("despamizer.worker.log_message", lambda message: None)

    worker = DespamizerWorker(build_config(tmp_path, dry_run=True), FakeClient)
    learned = []
    worker.classifier.spamassassin.learn = lambda message, message_class: learned.append(message_class) or True

    worker.run_once()

    assert learned == []


def test_worker_dry_run_does_not_learn_rescued_ham(monkeypatch, tmp_path):
    FakeClient.moved = []
    FakeClient.spam_messages = []
    rescued_message = EmailMessage(
        "1",
        "<rescued@example.com>",
        "promo@spam.example",
        "hello",
        "body",
    )
    FakeClient.messages = [rescued_message]
    monkeypatch.setattr("despamizer.worker.cleanup_logs", lambda days: None)
    monkeypatch.setattr("despamizer.worker.log_message", lambda message: None)

    worker = DespamizerWorker(build_config(tmp_path, dry_run=True), FakeClient)
    worker.state.record_moved_to_spam("test", rescued_message, "test")
    learned = []
    worker.classifier.spamassassin.learn = lambda message, message_class: learned.append(message_class) or True

    worker.run_once()

    assert learned == []
    assert FakeClient.moved == []
