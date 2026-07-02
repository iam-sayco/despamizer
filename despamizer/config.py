"""YAML configuration loading and validation."""

# Standard Library
import os
from pathlib import Path
import re

from .models import (
    AppConfig,
    AddressList,
    FilterRule,
    LearningSettings,
    MailboxConfig,
    RuleType,
    SpamAssassinSettings,
    SpamSettings,
    StateSettings,
    compile_rule_pattern,
)


def load_config(path: Path | str) -> AppConfig:
    """Load and validate application configuration from YAML."""
    import yaml

    with open(path, "r") as file:
        raw_config = yaml.safe_load(file) or {}
    if not isinstance(raw_config, dict):
        raise ValueError("Configuration root must be a mapping")
    return parse_config(raw_config)


def parse_config(raw_config: dict[str, object]) -> AppConfig:
    """Parse raw configuration mapping into typed config objects."""
    raw_mailboxes = raw_config.get("mailboxes", [])
    if not isinstance(raw_mailboxes, list) or not raw_mailboxes:
        raise ValueError("Configuration must define at least one mailbox")

    return AppConfig(
        poll_interval_seconds=_positive_int(
            _env("DESPAMIZER_WORKER_POLL_INTERVAL_SECONDS", "300"),
            "DESPAMIZER_WORKER_POLL_INTERVAL_SECONDS",
        ),
        dry_run=_bool_env("DESPAMIZER_WORKER_DRY_RUN", default=True),
        log_retention_days=_positive_int(
            _env("DESPAMIZER_LOG_RETENTION_DAYS", "30"),
            "DESPAMIZER_LOG_RETENTION_DAYS",
        ),
        state=_parse_state_settings(),
        spam=_parse_spam_settings(),
        mailboxes=[
            _parse_mailbox(mailbox, index)
            for index, mailbox in enumerate(raw_mailboxes, start=1)
        ],
    )


def _parse_mailbox(raw_mailbox: object, index: int) -> MailboxConfig:
    if not isinstance(raw_mailbox, dict):
        raise ValueError(f"mailboxes[{index}] must be a mapping")

    allowed_fields = {
        "name",
        "host",
        "port",
        "username",
        "password",
        "inbox_folder",
        "spam_folder",
        "whitelist",
        "blacklist",
        "rules",
    }
    unsupported_fields = set(raw_mailbox) - allowed_fields
    if unsupported_fields:
        fields = ", ".join(sorted(str(field) for field in unsupported_fields))
        raise ValueError(f"mailboxes[{index}] contains unsupported fields: {fields}")

    required_fields = [
        "name",
        "host",
        "port",
        "username",
        "password",
        "inbox_folder",
        "spam_folder",
    ]
    for field in required_fields:
        if not raw_mailbox.get(field):
            raise ValueError(f"mailboxes[{index}].{field} is required")

    return MailboxConfig(
        name=str(raw_mailbox["name"]),
        host=str(raw_mailbox["host"]),
        port=_positive_int(raw_mailbox["port"], f"mailboxes[{index}].port"),
        username=str(raw_mailbox["username"]),
        password=str(raw_mailbox["password"]),
        inbox_folder=str(raw_mailbox["inbox_folder"]),
        spam_folder=str(raw_mailbox["spam_folder"]),
        whitelist=_parse_address_list(raw_mailbox.get("whitelist", {}), index, "whitelist"),
        blacklist=_parse_address_list(raw_mailbox.get("blacklist", {}), index, "blacklist"),
        rules=_parse_rules(raw_mailbox.get("rules", []), index),
    )


def _parse_spam_settings() -> SpamSettings:
    required_score = _env("DESPAMIZER_SPAMASSASSIN_REQUIRED_SCORE", "")
    return SpamSettings(
        min_score=_number(
            _env("DESPAMIZER_SPAM_SCORE_MIN", "5.0"),
            "DESPAMIZER_SPAM_SCORE_MIN",
        ),
        spamassassin=SpamAssassinSettings(
            enabled=_bool_env("DESPAMIZER_SPAMASSASSIN_ENABLED", default=True),
            host=_env("DESPAMIZER_SPAMASSASSIN_HOST", "spamassassin"),
            port=_positive_int(
                _env("DESPAMIZER_SPAMASSASSIN_PORT", "783"),
                "DESPAMIZER_SPAMASSASSIN_PORT",
            ),
            timeout_seconds=_positive_int(
                _env("DESPAMIZER_SPAMASSASSIN_TIMEOUT_SECONDS", "15"),
                "DESPAMIZER_SPAMASSASSIN_TIMEOUT_SECONDS",
            ),
            required_score=None
            if not required_score
            else _number(required_score, "DESPAMIZER_SPAMASSASSIN_REQUIRED_SCORE"),
        ),
        learning=LearningSettings(
            enabled=_bool_env("DESPAMIZER_LEARNING_ENABLED", default=True),
            learn_rescued_ham=_bool_env("DESPAMIZER_LEARNING_RESCUED_HAM", default=True),
            learn_manual_spam=_bool_env("DESPAMIZER_LEARNING_MANUAL_SPAM", default=True),
            scan_spam_folder=_bool_env("DESPAMIZER_LEARNING_SCAN_SPAM_FOLDER", default=True),
            max_spam_folder_messages_per_run=_positive_int(
                _env("DESPAMIZER_LEARNING_SPAM_FOLDER_MESSAGES_MAX", "100"),
                "DESPAMIZER_LEARNING_SPAM_FOLDER_MESSAGES_MAX",
            ),
        ),
    )


def _parse_state_settings() -> StateSettings:
    return StateSettings(
        path=_env("DESPAMIZER_STATE_PATH", "/app/state/despamizer.sqlite"),
        retention_days=_positive_int(
            _env("DESPAMIZER_STATE_RETENTION_DAYS", "365"),
            "DESPAMIZER_STATE_RETENTION_DAYS",
        ),
    )


def _parse_address_list(raw_list: object, mailbox_index: int, field: str) -> AddressList:
    if raw_list is None:
        return AddressList()
    if not isinstance(raw_list, dict):
        raise ValueError(f"mailboxes[{mailbox_index}].{field} must be a mapping")
    return AddressList(
        senders=_parse_string_list(
            raw_list.get("senders", []),
            f"mailboxes[{mailbox_index}].{field}.senders",
        ),
        domains=[
            domain.lower()
            for domain in _parse_string_list(
                raw_list.get("domains", []),
                f"mailboxes[{mailbox_index}].{field}.domains",
            )
        ],
    )


def _parse_string_list(raw_list: object, field: str) -> list[str]:
    if raw_list is None:
        return []
    if not isinstance(raw_list, list):
        raise ValueError(f"{field} must be a list")
    return [str(item).lower() for item in raw_list]


def _parse_rules(raw_rules: object, mailbox_index: int) -> list[FilterRule]:
    if raw_rules is None:
        return []
    if not isinstance(raw_rules, list):
        raise ValueError(f"mailboxes[{mailbox_index}].rules must be a list")

    rules = []
    for rule_index, raw_rule in enumerate(raw_rules, start=1):
        if not isinstance(raw_rule, dict):
            raise ValueError(
                f"mailboxes[{mailbox_index}].rules[{rule_index}] must be a mapping"
            )
        try:
            rule_type = RuleType(str(raw_rule["type"]))
        except KeyError as exc:
            raise ValueError(
                f"mailboxes[{mailbox_index}].rules[{rule_index}].type is required"
            ) from exc
        except ValueError as exc:
            allowed = ", ".join(rule.value for rule in RuleType)
            raise ValueError(
                f"mailboxes[{mailbox_index}].rules[{rule_index}].type must be one of: {allowed}"
            ) from exc

        if not raw_rule.get("pattern"):
            raise ValueError(
                f"mailboxes[{mailbox_index}].rules[{rule_index}].pattern is required"
            )

        try:
            pattern = compile_rule_pattern(str(raw_rule["pattern"]))
        except re.error as exc:
            raise ValueError(
                f"mailboxes[{mailbox_index}].rules[{rule_index}].pattern is invalid: {exc}"
            ) from exc

        rules.append(
            FilterRule(
                type=rule_type,
                pattern=pattern,
                score=_number(
                    raw_rule.get("score", 10.0),
                    f"mailboxes[{mailbox_index}].rules[{rule_index}].score",
                ),
            )
        )
    return rules


def _positive_int(value: object, field: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise ValueError(f"{field} must be greater than 0")
    return parsed


def _number(value: object, field: str) -> float:
    parsed = float(value)
    if parsed < 0:
        raise ValueError(f"{field} must not be negative")
    return parsed


def _env(name: str, default: str) -> str:
    return os.getenv(name, default).strip()


def _bool_env(name: str, *, default: bool) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None or not raw_value.strip():
        return default
    value = raw_value.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean value")
