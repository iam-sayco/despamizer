from pathlib import Path
import tempfile

from despamizer.logger import cleanup_logs, log_message


def test_log_message_creates_file(monkeypatch):
    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = Path(tmpdir) / "test.log"
        monkeypatch.setattr("despamizer.logger.log_file", log_path)
        log_message("test entry")
        assert log_path.exists()
        assert "test entry" in log_path.read_text()


def test_log_message_prints_if_verbose(monkeypatch, capsys):
    monkeypatch.setattr("despamizer.logger.VERBOSE", True)
    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = Path(tmpdir) / "test.log"
        monkeypatch.setattr("despamizer.logger.log_file", log_path)
        log_message("visible entry")
        captured = capsys.readouterr()
        assert "visible entry" in captured.out


def test_log_message_escapes_control_characters(monkeypatch):
    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = Path(tmpdir) / "test.log"
        monkeypatch.setattr("despamizer.logger.log_file", log_path)
        log_message("subject\r\n[FAKE] injected\tvalue")

        lines = log_path.read_text().splitlines()
        assert len(lines) == 1
        assert "\\r\\n[FAKE] injected\\tvalue" in lines[0]


def test_cleanup_logs(monkeypatch):
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        monkeypatch.setattr("despamizer.logger.LOG_DIR", tmp_path)
        monkeypatch.setattr("despamizer.logger.log_file", tmp_path / "dummy.log")
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
