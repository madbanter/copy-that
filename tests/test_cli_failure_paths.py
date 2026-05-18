import pytest
import logging
from unittest.mock import patch, MagicMock
from copy_that.main import app
from typer.testing import CliRunner

runner = CliRunner()

def test_stop_command_neither_flag(caplog):
    with caplog.at_level(logging.WARNING):
        result = runner.invoke(app, ["stop"])
    assert result.exit_code == 0
    assert "Please specify which process to stop" in caplog.text

@patch("copy_that.main.stop_process")
def test_stop_command_both_stopped(mock_stop, caplog):
    mock_stop.return_value = True
    
    with caplog.at_level(logging.INFO):
        result = runner.invoke(app, ["stop", "--watch", "--auto-mount"])
    assert result.exit_code == 0
    assert "Stopped watch process" in caplog.text
    assert "Stopped auto-mount process" in caplog.text

@patch("copy_that.main.setup_logging")
@patch("copy_that.main.is_process_running")
def test_auto_mount_already_running(mock_is_running, mock_setup_logging, tmp_path, caplog):
    mock_is_running.return_value = True
    
    with caplog.at_level(logging.ERROR):
        result = runner.invoke(app, ["auto-mount", "--dest", str(tmp_path / "dest")])
        
    assert result.exit_code == 1
    assert "Error: An auto-mount process is already running" in caplog.text
