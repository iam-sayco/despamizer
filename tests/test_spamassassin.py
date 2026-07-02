from despamizer.models import EmailMessage, SpamAssassinSettings
from despamizer.spamassassin import SpamAssassinClient, _parse_response


class FakeSocket:
    def __init__(self, chunks):
        self.chunks = list(chunks)
        self.sent = b""
        self.timeout = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return None

    def settimeout(self, timeout):
        self.timeout = timeout

    def sendall(self, payload):
        self.sent += payload

    def recv(self, size):
        if not self.chunks:
            return b""
        return self.chunks.pop(0)


def test_parse_response_reads_spamd_score():
    result = _parse_response("SPAMD/1.5 0 EX_OK\r\nSpam: True ; 7.2 / 5.0\r\n\r\n")

    assert result.available is True
    assert result.is_spam is True
    assert result.score == 7.2
    assert result.required_score == 5.0


def test_client_sends_check_request(monkeypatch):
    fake_socket = FakeSocket(
        [b"SPAMD/1.5 0 EX_OK\r\nSpam: False ; 1.0 / 5.0\r\n\r\n"]
    )
    calls = []

    def fake_create_connection(address, timeout):
        calls.append((address, timeout))
        return fake_socket

    monkeypatch.setattr("despamizer.spamassassin.socket.create_connection", fake_create_connection)

    client = SpamAssassinClient(
        SpamAssassinSettings(
            enabled=True,
            host="spamassassin",
            port=783,
            timeout_seconds=12,
        )
    )
    result = client.check(
        EmailMessage(
            uid="1",
            message_id="<sender-1@example.com>",
            sender="sender@example.com",
            subject="hello",
            body="body",
            raw=b"From: sender@example.com\r\n\r\nbody",
        )
    )

    assert calls == [(("spamassassin", 783), 12)]
    assert fake_socket.sent.startswith(b"CHECK SPAMC/1.5\r\nContent-length:")
    assert result.available is True
    assert result.is_spam is False


def test_client_returns_unavailable_on_connection_error(monkeypatch):
    monkeypatch.setattr(
        "despamizer.spamassassin.socket.create_connection",
        lambda address, timeout: (_ for _ in ()).throw(OSError("refused")),
    )
    monkeypatch.setattr("despamizer.spamassassin.log_message", lambda message: None)

    client = SpamAssassinClient(SpamAssassinSettings(enabled=True))
    result = client.check(EmailMessage("1", "<a@example.com>", "a@example.com", "hello", "body"))

    assert result.available is False


def test_client_sends_tell_request_for_learning(monkeypatch):
    fake_socket = FakeSocket([b"SPAMD/1.5 0 EX_OK\r\n\r\n"])

    monkeypatch.setattr(
        "despamizer.spamassassin.socket.create_connection",
        lambda address, timeout: fake_socket,
    )

    client = SpamAssassinClient(SpamAssassinSettings(enabled=True))
    learned = client.learn(
        EmailMessage("1", "<learn@example.com>", "sender@example.com", "hello", "body"),
        "spam",
    )

    assert learned is True
    assert fake_socket.sent.startswith(b"TELL SPAMC/1.5\r\nContent-length:")
    assert b"Message-class: spam" in fake_socket.sent
    assert b"Set: local" in fake_socket.sent
