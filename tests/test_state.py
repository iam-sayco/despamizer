from despamizer.models import EmailMessage, StateSettings
from despamizer.state import MAX_STORED_TEXT_CHARS, MessageState, WorkerState, fingerprint_message

from sqlmodel import Session, select


def test_state_creates_sqlite_file_and_tracks_message(tmp_path):
    state_path = tmp_path / "nested" / "despamizer.sqlite"
    state = WorkerState(StateSettings(path=str(state_path), retention_days=365))
    message = EmailMessage(
        uid="1",
        message_id="<message@example.com>",
        sender="sender@example.com",
        subject="hello",
        body="body",
    )

    state.record_moved_to_spam("personal", message, "rule")

    assert state_path.exists()
    assert state.was_moved_to_spam("personal", message) is True


def test_state_uses_message_id_for_stable_fingerprint():
    first = EmailMessage("1", "<same@example.com>", "a@example.com", "hello", "one")
    second = EmailMessage("2", "<same@example.com>", "b@example.com", "other", "two")

    assert fingerprint_message(first) == fingerprint_message(second)


def test_state_cleanup_removes_expired_rows(tmp_path):
    state = WorkerState(
        StateSettings(path=str(tmp_path / "despamizer.sqlite"), retention_days=1)
    )
    message = EmailMessage("1", "<old@example.com>", "a@example.com", "hello", "body")
    state.record_moved_to_spam("personal", message, "rule")

    row_count = state.cleanup()

    assert row_count == 0


def test_state_truncates_untrusted_metadata(tmp_path):
    state = WorkerState(
        StateSettings(path=str(tmp_path / "despamizer.sqlite"), retention_days=365)
    )
    long_text = "x" * (MAX_STORED_TEXT_CHARS + 100)
    message = EmailMessage("1", long_text, long_text, long_text, "body")

    state.record_moved_to_spam("personal", message, long_text)

    with Session(state.engine) as session:
        row = session.exec(select(MessageState)).one()

    assert len(row.message_id) == MAX_STORED_TEXT_CHARS
    assert len(row.sender) == MAX_STORED_TEXT_CHARS
    assert len(row.subject) == MAX_STORED_TEXT_CHARS
    assert len(row.reason) == MAX_STORED_TEXT_CHARS
