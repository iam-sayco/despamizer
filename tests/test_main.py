from despamizer import __main__
from despamizer.models import AppConfig, MailboxConfig, SpamSettings, StateSettings


def build_config():
    mailbox = MailboxConfig(
        name="personal",
        host="imap.example.com",
        port=993,
        username="user@example.com",
        password="secret",
        inbox_folder="INBOX",
        spam_folder="Junk",
    )
    return AppConfig(
        poll_interval_seconds=300,
        dry_run=False,
        log_retention_days=30,
        state=StateSettings(path="/tmp/despamizer-test.sqlite"),
        spam=SpamSettings(),
        mailboxes=[mailbox],
    )


def test_main_lists_folders(monkeypatch, capsys):
    class FakeClient:
        def __init__(self, mailbox):
            self.mailbox = mailbox

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return None

        def list_folders(self):
            return ["INBOX", "Junk"]

    monkeypatch.setattr(__main__, "load_config", lambda path: build_config())
    monkeypatch.setattr(__main__, "ImapMailboxClient", FakeClient)
    monkeypatch.setattr(
        "sys.argv",
        ["despamizer", "--config", "config.yaml", "folders", "personal"],
    )

    __main__.main()

    captured = capsys.readouterr()
    assert captured.out.splitlines() == ["INBOX", "Junk"]


def test_main_run_dry_overrides_config(monkeypatch):
    class FakeWorker:
        received_config = None

        def __init__(self, config):
            self.received_config = config
            FakeWorker.received_config = config

        def run_once(self):
            return None

    monkeypatch.setattr(__main__, "load_config", lambda path: build_config())
    monkeypatch.setattr(__main__, "DespamizerWorker", FakeWorker)
    monkeypatch.setattr(__main__, "log_message", lambda message: None)
    monkeypatch.setattr(
        "sys.argv",
        ["despamizer", "--config", "config.yaml", "--run-dry", "once"],
    )

    __main__.main()

    assert FakeWorker.received_config.dry_run is True
