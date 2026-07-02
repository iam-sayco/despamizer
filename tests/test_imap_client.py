import sys
import types

from despamizer.imap_client import ImapMailboxClient
from despamizer.models import MailboxConfig


class FakeMailBox:
    calls = []

    def __init__(self, host, port):
        self.calls.append((self.__class__.__name__, host, port))


def build_mailbox_config():
    return MailboxConfig(
        name="test",
        host="imap.example.com",
        port=993,
        username="user@example.com",
        password="secret",
        inbox_folder="INBOX",
        spam_folder="Junk",
    )


def test_imap_client_uses_ssl_mailbox_class(monkeypatch):
    fake_module = types.SimpleNamespace(
        MailBox=FakeMailBox,
    )
    FakeMailBox.calls = []
    monkeypatch.setitem(sys.modules, "imap_tools", fake_module)

    ImapMailboxClient(build_mailbox_config())

    assert FakeMailBox.calls == [("FakeMailBox", "imap.example.com", 993)]
