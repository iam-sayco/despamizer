"""Logging utilities for despamizer."""

# Standard Library
import datetime
import os

from .settings import PROJECT_DIR, VERBOSE

LOG_DIR = PROJECT_DIR / "logs"
MAX_LOG_MESSAGE_CHARS = 4000
os.makedirs(LOG_DIR, exist_ok=True)
log_file = LOG_DIR / f"{datetime.date.today()}.log"


def log_message(message: str) -> None:
    """Log a message to today's log file."""
    timestamp = datetime.datetime.now().strftime("[%Y-%m-%d %H:%M:%S]")
    log_line = f"{timestamp} {_sanitize_log_message(message)}"
    with open(log_file, "a") as log:
        log.write(f"{log_line}\n")
    if VERBOSE:
        print(log_line)  # noqa: T201


def _sanitize_log_message(message: str) -> str:
    sanitized = []
    for char in message:
        codepoint = ord(char)
        if char == "\n":
            sanitized.append("\\n")
        elif char == "\r":
            sanitized.append("\\r")
        elif char == "\t":
            sanitized.append("\\t")
        elif codepoint < 32 or codepoint == 127:
            sanitized.append(f"\\x{codepoint:02x}")
        else:
            sanitized.append(char)
    value = "".join(sanitized)
    if len(value) > MAX_LOG_MESSAGE_CHARS:
        return f"{value[:MAX_LOG_MESSAGE_CHARS]}...[truncated]"
    return value


def cleanup_logs(days: int = 30) -> None:
    """Delete log files older than `days` days."""
    now = datetime.datetime.now()
    for file in os.listdir(LOG_DIR):
        if not file.endswith(".log"):
            continue
        file_path = LOG_DIR / file
        if file_path.is_file():
            file_date = datetime.datetime.strptime(file, "%Y-%m-%d.log")
            if (now - file_date).days > days:
                file_path.unlink()
                log_message(f"Deleted old log: {file}")
