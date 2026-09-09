import pytest
import logging
from unittest.mock import patch, MagicMock
from copy_that.main import app
from typer.testing import CliRunner

runner = CliRunner()

@patch("copy_that.main.stop_process")
def test_stop_command_all_default(mock_stop, caplog):
    mock_stop.return_value = True
    with caplog.at_level(logging.INFO):
        result = runner.invoke(app, ["stop"])
    assert result.exit_code == 0
    assert "Stopped watch process" in caplog.text
    assert "Stopped auto-mount process" in caplog.text

@patch("copy_that.main.stop_process")
def test_stop_command_both_stopped(mock_stop, caplog):
    mock_stop.return_value = True
    
    with caplog.at_level(logging.INFO):
        result = runner.invoke(app, ["stop", "--watch", "--auto-mount"])
    assert result.exit_code == 0
    assert "Stopped watch process" in caplog.text
    assert "Stopped auto-mount process" in caplog.text

@patch("copy_that.main.setup_logging")
@patch("copy_that.main.ProcessLock")
def test_auto_mount_already_running(mock_lock_class, mock_setup_logging, tmp_path, caplog):
    mock_lock = MagicMock()
    mock_lock.__enter__.side_effect = RuntimeError("Unable to acquire process lock")
    mock_lock_class.return_value = mock_lock
    
    with caplog.at_level(logging.ERROR):
        result = runner.invoke(app, ["auto-mount", "--dest", str(tmp_path / "dest")])
        
    assert result.exit_code == 1
    assert "Error: An auto-mount process is already running" in caplog.text
