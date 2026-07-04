import datetime
import sys
import types

from despamizer.imap_client import ImapMailboxClient
from despamizer.models import MailboxConfig


class FakeMailBox:
    calls = []
    fetch_calls = []
    deleted = []
    expunged = False

    def __init__(self, host, port):
        self.folder = types.SimpleNamespace(set=lambda folder_name: None)
        self.calls.append((self.__class__.__name__, host, port))

    def fetch(self, *args, **kwargs):
        self.fetch_calls.append((args, kwargs))
        return iter([])

    def delete(self, uid_list):
        self.deleted.append(uid_list)

    def expunge(self):
        self.__class__.expunged = True


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


def test_iter_inbox_messages_fetches_headers_only(monkeypatch):
    fake_module = types.SimpleNamespace(
        MailBox=FakeMailBox,
    )
    FakeMailBox.fetch_calls = []
    monkeypatch.setitem(sys.modules, "imap_tools", fake_module)

    client = ImapMailboxClient(build_mailbox_config())
    client.iter_inbox_messages()

    assert FakeMailBox.fetch_calls == [
        (("ALL",), {"mark_seen": False, "headers_only": True, "bulk": True})
    ]


def test_get_inbox_message_fetches_single_full_message_by_uid(monkeypatch):
    class Message:
        uid = "42"
        from_ = "sender@example.com"
        subject = "hello"
        text = "body"
        html = ""
        date = datetime.datetime.now(datetime.UTC)

        class obj:
            @staticmethod
            def as_bytes():
                return b"Message-ID: <x@example.com>\r\n\r\nbody"

            @staticmethod
            def get(name, default=""):
                return "<x@example.com>" if name == "Message-ID" else default

    class MailBoxWithMessage(FakeMailBox):
        def fetch(self, *args, **kwargs):
            self.fetch_calls.append((args, kwargs))
            return iter([Message()])

    fake_module = types.SimpleNamespace(
        MailBox=MailBoxWithMessage,
    )
    MailBoxWithMessage.fetch_calls = []
    monkeypatch.setitem(sys.modules, "imap_tools", fake_module)

    client = ImapMailboxClient(build_mailbox_config())
    message = client.get_inbox_message("42")

    assert MailBoxWithMessage.fetch_calls == [
        (("UID 42",), {"mark_seen": False, "bulk": False})
    ]
    assert message.body == "body"
    assert message.raw == b"Message-ID: <x@example.com>\r\n\r\nbody"


def test_iter_spam_messages_streams_without_bulk(monkeypatch):
    fake_module = types.SimpleNamespace(
        MailBox=FakeMailBox,
    )
    FakeMailBox.fetch_calls = []
    monkeypatch.setitem(sys.modules, "imap_tools", fake_module)

    client = ImapMailboxClient(build_mailbox_config())
    client.iter_spam_messages(limit=10)

    assert FakeMailBox.fetch_calls == [(("ALL",), {"mark_seen": False, "bulk": False})]


def test_delete_old_spam_messages_deletes_and_expunges(monkeypatch):
    class OldMessage:
        uid = "10"
        from_ = "sender@example.com"
        subject = "old"
        text = ""
        html = ""
        date = datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=31)

        class obj:
            @staticmethod
            def get(name, default=""):
                return "<old@example.com>" if name == "Message-ID" else default

    class NewMessage:
        uid = "11"
        from_ = "sender@example.com"
        subject = "new"
        text = ""
        html = ""
        date = datetime.datetime.now(datetime.UTC)

        class obj:
            @staticmethod
            def get(name, default=""):
                return "<new@example.com>" if name == "Message-ID" else default

    class MailBoxWithSpam(FakeMailBox):
        def fetch(self, *args, **kwargs):
            self.fetch_calls.append((args, kwargs))
            return iter([OldMessage(), NewMessage()])

    fake_module = types.SimpleNamespace(
        MailBox=MailBoxWithSpam,
    )
    MailBoxWithSpam.fetch_calls = []
    MailBoxWithSpam.deleted = []
    MailBoxWithSpam.expunged = False
    monkeypatch.setitem(sys.modules, "imap_tools", fake_module)

    client = ImapMailboxClient(build_mailbox_config())
    deleted_messages = client.delete_old_spam_messages(30)

    assert [message.uid for message in deleted_messages] == ["10"]
    criteria, fetch_options = MailBoxWithSpam.fetch_calls[0]
    assert criteria[0].startswith("BEFORE ")
    assert fetch_options == {"mark_seen": False, "headers_only": True, "bulk": True}
    assert MailBoxWithSpam.deleted == [["10"]]
    assert MailBoxWithSpam.expunged is True
