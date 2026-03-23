import logging
import pytest
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock
from copy_that.main import OutputFilter, main

@pytest.fixture(autouse=True)
def restore_logging():
    """
    Ensure logging handlers are restored after each test.
    This prevents main()'s reconfiguration from breaking pytest's caplog/output.
    """
    root_logger = logging.getLogger()
    original_handlers = root_logger.handlers[:]
    original_level = root_logger.level
    
    yield
    
    # Restore
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
        if hasattr(handler, "close"):
            handler.close()
    
    for handler in original_handlers:
        root_logger.addHandler(handler)
    root_logger.setLevel(original_level)

def test_output_filter_minimal():
    filter_min = OutputFilter("minimal")
    
    # Errors should pass
    record_error = logging.LogRecord("test", logging.ERROR, "path", 10, "msg", None, None)
    assert filter_min.filter(record_error) is True
    
    # Info should be blocked
    record_info = logging.LogRecord("test", logging.INFO, "path", 10, "msg", None, None)
    assert filter_min.filter(record_info) is False
    
    # Summary should pass regardless
    record_summary = logging.LogRecord("test", logging.INFO, "path", 10, "Sync Summary", None, None)
    assert filter_min.filter(record_summary) is True

def test_output_filter_normal():
    filter_norm = OutputFilter("normal")
    
    # Info should pass
    record_info = logging.LogRecord("test", logging.INFO, "path", 10, "msg", None, None)
    assert filter_norm.filter(record_info) is True
    
    # Debug should be blocked
    record_debug = logging.LogRecord("test", logging.DEBUG, "path", 10, "msg", None, None)
    assert filter_norm.filter(record_debug) is False

def test_output_filter_verbose():
    filter_verb = OutputFilter("verbose")
    
    # Debug should pass
    record_debug = logging.LogRecord("test", logging.DEBUG, "path", 10, "msg", None, None)
    assert filter_verb.filter(record_debug) is True

def test_logging_setup_file_handler(tmp_path, monkeypatch):
    log_file = tmp_path / "audit.log"
    source_dir = tmp_path / "src"
    source_dir.mkdir()
    dest_dir = tmp_path / "dest"
    
    # Mock sys.argv
    monkeypatch.setattr("sys.argv", [
        "copy-that",
        "--source", str(source_dir),
        "--dest", str(dest_dir),
        "--log-file", str(log_file),
        "--dry-run"
    ])
    
    with pytest.raises(SystemExit) as e:
        main()
    assert e.value.code == 0
    
    # Check if log file was created
    assert log_file.exists()
    content = log_file.read_text()
    assert "Source:" in content
    assert "Destination:" in content

def test_logging_setup_file_error(tmp_path, monkeypatch, capsys):
    # Use a directory where we can't create files
    # Note: On macOS /proc doesn't exist, but we just need any non-writable path
    forbidden_file = Path("/nonexistent_dir_random_name/forbidden.log")
    source_dir = tmp_path / "src"
    source_dir.mkdir()
    dest_dir = tmp_path / "dest"
    
    monkeypatch.setattr("sys.argv", [
        "copy-that",
        "--source", str(source_dir),
        "--dest", str(dest_dir),
        "--log-file", str(forbidden_file),
        "--dry-run"
    ])
    
    with pytest.raises(SystemExit) as e:
        main()
    
    captured = capsys.readouterr()
    assert "Could not initialize log file" in captured.err
