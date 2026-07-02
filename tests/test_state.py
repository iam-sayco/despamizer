from despamizer.models import EmailMessage, StateSettings
from despamizer.state import WorkerState, fingerprint_message


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
