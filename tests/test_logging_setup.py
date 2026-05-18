import logging
import pytest
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock
from copy_that.main import main

def test_logging_setup_file_handler_no_dry_run(tmp_path, monkeypatch):
    log_file = tmp_path / "audit.log"
    source_dir = tmp_path / "src"
    source_dir.mkdir()
    dest_dir = tmp_path / "dest"
    
    # Mock sys.argv for real sync
    monkeypatch.setattr("sys.argv", [
        "copy-that",
        "sync",
        "--source", str(source_dir),
        "--dest", str(dest_dir),
        "--log-file", str(log_file),
        "--no-space-check"
    ])
    
    with pytest.raises(SystemExit) as e:
        main()
    assert e.value.code == 0
    
    # Check if log file was created
    assert log_file.exists()
    content = log_file.read_text()
    assert "Source:" in content
    assert "Destination:" in content

def test_logging_setup_file_handler_dry_run_no_log(tmp_path, monkeypatch):
    log_file = tmp_path / "audit.log"
    source_dir = tmp_path / "src"
    source_dir.mkdir()
    dest_dir = tmp_path / "dest"
    
    # Mock sys.argv for dry run (default verbosity)
    monkeypatch.setattr("sys.argv", [
        "copy-that",
        "sync",
        "--source", str(source_dir),
        "--dest", str(dest_dir),
        "--log-file", str(log_file),
        "--dry-run"
    ])
    
    with pytest.raises(SystemExit) as e:
        main()
    assert e.value.code == 0
    
    # Log file should NOT be created for dry run by default
    assert not log_file.exists()

def test_logging_setup_file_handler_dry_run_verbose_log(tmp_path, monkeypatch):
    log_file = tmp_path / "audit.log"
    source_dir = tmp_path / "src"
    source_dir.mkdir()
    dest_dir = tmp_path / "dest"
    
    # Mock sys.argv for dry run with verbose
    monkeypatch.setattr("sys.argv", [
        "copy-that",
        "sync",
        "--source", str(source_dir),
        "--dest", str(dest_dir),
        "--log-file", str(log_file),
        "--dry-run",
        "-v"
    ])
    
    with pytest.raises(SystemExit) as e:
        main()
    assert e.value.code == 0
    
    # Log file SHOULD be created for dry run if verbose
    assert log_file.exists()

def test_logging_setup_file_error(tmp_path, monkeypatch, capsys):
    source_dir = tmp_path / "src"
    source_dir.mkdir()
    dest_dir = tmp_path / "dest"
    log_file = tmp_path / "wont_work.log"
    
    monkeypatch.setattr("sys.argv", [
        "copy-that",
        "sync",
        "--source", str(source_dir),
        "--dest", str(dest_dir),
        "--log-file", str(log_file),
        "--no-space-check"
    ])
    
    # Mock RotatingFileHandler to raise an error during initialization
    with patch("copy_that.main.RotatingFileHandler", side_effect=PermissionError("Mocked permission error")):
        with pytest.raises(SystemExit) as e:
            main()
        assert e.value.code == 0 # Non-fatal error
    
    captured = capsys.readouterr()
    assert "Could not initialize log file" in captured.err
    assert "Mocked permission error" in captured.err
