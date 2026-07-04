import datetime
from pathlib import Path
import tempfile

from despamizer.logger import _current_log_file, cleanup_logs, log_message


def test_log_message_creates_file(monkeypatch):
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        monkeypatch.setattr("despamizer.logger.LOG_DIR", tmp_path)
        log_message("test entry")
        log_path = next(tmp_path.glob("*.log"))
        assert log_path.exists()
        assert "test entry" in log_path.read_text()


def test_log_message_prints_if_verbose(monkeypatch, capsys):
    monkeypatch.setattr("despamizer.logger.VERBOSE", True)
    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setattr("despamizer.logger.LOG_DIR", Path(tmpdir))
        log_message("visible entry")
        captured = capsys.readouterr()
        assert "visible entry" in captured.out


def test_log_message_escapes_control_characters(monkeypatch):
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        monkeypatch.setattr("despamizer.logger.LOG_DIR", tmp_path)
        log_message("subject\r\n[FAKE] injected\tvalue")

        log_path = next(tmp_path.glob("*.log"))
        lines = log_path.read_text().splitlines()
        assert len(lines) == 1
        assert "\\r\\n[FAKE] injected\\tvalue" in lines[0]


def test_current_log_file_uses_current_date(monkeypatch):
    class FakeDate(datetime.date):
        current = datetime.date(2026, 7, 4)

        @classmethod
        def today(cls):
            return cls.current

    monkeypatch.setattr("despamizer.logger.datetime.date", FakeDate)

    assert _current_log_file().name == "2026-07-04.log"

    FakeDate.current = datetime.date(2026, 7, 5)

    assert _current_log_file().name == "2026-07-05.log"


def test_cleanup_logs(monkeypatch):
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        monkeypatch.setattr("despamizer.logger.LOG_DIR", tmp_path)
        old_log = tmp_path / "2000-01-01.log"
        old_log.write_text("old")
        new_log = tmp_path / "2999-01-01.log"
        new_log.write_text("new")
        cleanup_logs(days=30)
        assert not old_log.exists()
        assert new_log.exists()


def test_cleanup_logs_ignores_malformed_log_names(monkeypatch):
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        monkeypatch.setattr("despamizer.logger.LOG_DIR", tmp_path)
        malformed_log = tmp_path / "not-a-date.log"
        malformed_log.write_text("entry")

        cleanup_logs(days=30)

        assert malformed_log.exists()
