import pytest

from despamizer.config import parse_config
from despamizer.models import RuleType


def valid_config():
    return {
        "mailboxes": [
            {
                "name": "test",
                "host": "imap.example.com",
                "port": 993,
                "username": "user@example.com",
                "password": "secret",
                "inbox_folder": "INBOX",
                "spam_folder": "Junk",
                "whitelist": {"senders": ["friend@example.com"]},
                "blacklist": {"domains": ["spam.example"]},
                "rules": [
                    {"type": "sender", "pattern": "@spam\\.example$", "score": 10}
                ],
            }
        ],
    }


def test_parse_config_builds_typed_config(monkeypatch):
    monkeypatch.setenv("DESPAMIZER_WORKER_POLL_INTERVAL_SECONDS", "60")
    monkeypatch.setenv("DESPAMIZER_WORKER_DRY_RUN", "true")
    monkeypatch.setenv("DESPAMIZER_LOG_RETENTION_DAYS", "7")
    monkeypatch.setenv("DESPAMIZER_STATE_PATH", "/app/state/test.sqlite")
    monkeypatch.setenv("DESPAMIZER_STATE_RETENTION_DAYS", "180")
    monkeypatch.setenv("DESPAMIZER_SPAM_SCORE_MIN", "5")
    monkeypatch.setenv("DESPAMIZER_SPAMASSASSIN_HOST", "spamassassin")
    monkeypatch.setenv("DESPAMIZER_LEARNING_SPAM_FOLDER_MESSAGES_MAX", "50")

    config = parse_config(valid_config())

    assert config.poll_interval_seconds == 60
    assert config.dry_run is True
    assert config.spam.min_score == 5
    assert config.state.path == "/app/state/test.sqlite"
    assert config.state.retention_days == 180
    assert config.spam.spamassassin.host == "spamassassin"
    assert config.spam.learning.max_spam_folder_messages_per_run == 50
    assert config.mailboxes[0].whitelist.senders == ["friend@example.com"]
    assert config.mailboxes[0].blacklist.domains == ["spam.example"]
    assert config.mailboxes[0].rules[0].type == RuleType.SENDER


def test_parse_config_requires_mailboxes():
    raw_config = valid_config()
    raw_config["mailboxes"] = []

    with pytest.raises(ValueError, match="at least one mailbox"):
        parse_config(raw_config)


def test_parse_config_rejects_invalid_rule_type():
    raw_config = valid_config()
    raw_config["mailboxes"][0]["rules"][0]["type"] = "unknown"

    with pytest.raises(ValueError, match="must be one of"):
        parse_config(raw_config)


def test_parse_config_rejects_invalid_regex_before_imap_use():
    raw_config = valid_config()
    raw_config["mailboxes"][0]["rules"][0]["pattern"] = "["

    with pytest.raises(ValueError, match="pattern is invalid"):
        parse_config(raw_config)


def test_parse_config_rejects_invalid_whitelist():
    raw_config = valid_config()
    raw_config["mailboxes"][0]["whitelist"] = []

    with pytest.raises(ValueError, match="whitelist must be a mapping"):
        parse_config(raw_config)


def test_parse_config_rejects_unsupported_mailbox_fields():
    raw_config = valid_config()
    raw_config["mailboxes"][0]["ssl"] = False

    with pytest.raises(ValueError, match="unsupported fields: ssl"):
        parse_config(raw_config)


def test_parse_config_uses_safe_runtime_defaults(monkeypatch):
    for name in [
        "DESPAMIZER_WORKER_POLL_INTERVAL_SECONDS",
        "DESPAMIZER_WORKER_DRY_RUN",
        "DESPAMIZER_LOG_RETENTION_DAYS",
        "DESPAMIZER_STATE_PATH",
        "DESPAMIZER_STATE_RETENTION_DAYS",
        "DESPAMIZER_SPAM_SCORE_MIN",
        "DESPAMIZER_SPAMASSASSIN_HOST",
        "DESPAMIZER_LEARNING_SPAM_FOLDER_MESSAGES_MAX",
    ]:
        monkeypatch.delenv(name, raising=False)

    config = parse_config(valid_config())

    assert config.poll_interval_seconds == 300
    assert config.dry_run is True
    assert config.state.path == "/app/state/despamizer.sqlite"


def test_parse_config_rejects_invalid_env_bool(monkeypatch):
    monkeypatch.setenv("DESPAMIZER_WORKER_DRY_RUN", "maybe")

    with pytest.raises(ValueError, match="DESPAMIZER_WORKER_DRY_RUN"):
        parse_config(valid_config())
