import pytest
import time
import json
import signal
import os
import logging
from pathlib import Path
from unittest.mock import MagicMock, patch
from copy_that.main import app
from typer.testing import CliRunner

runner = CliRunner()

def test_stop_command_no_args(caplog):
    with caplog.at_level(logging.WARNING):
        result = runner.invoke(app, ["stop"])
    assert result.exit_code == 0
    assert "Please specify which process to stop" in caplog.text

def test_stop_command_watch_not_running(caplog):
    with caplog.at_level(logging.INFO):
        result = runner.invoke(app, ["stop", "--watch"])
    assert result.exit_code == 0
    assert "No active watch process found" in caplog.text

@patch("copy_that.main.stop_process")
def test_stop_command_watch_running(mock_stop, caplog):
    mock_stop.return_value = True
    
    with caplog.at_level(logging.INFO):
        result = runner.invoke(app, ["stop", "--watch"])
    assert result.exit_code == 0
    assert "Stopped watch process" in caplog.text
    mock_stop.assert_called_once_with("watch")

@patch("copy_that.main.stop_process")
def test_stop_command_auto_mount_running(mock_stop, caplog):
    mock_stop.return_value = True
    
    with caplog.at_level(logging.INFO):
        result = runner.invoke(app, ["stop", "--auto-mount"])
    assert result.exit_code == 0
    assert "Stopped auto-mount process" in caplog.text
    mock_stop.assert_called_once_with("auto-mount")

@patch("copy_that.main.Monitor")
@patch("copy_that.main.write_pid_file")
@patch("copy_that.main.remove_pid_file")
@patch("copy_that.main.is_process_running")
def test_watch_command_basic(mock_is_running, mock_remove_pid, mock_write_pid, mock_monitor_class, tmp_path):
    mock_is_running.return_value = False
    source = tmp_path / "src"
    source.mkdir()
    dest = tmp_path / "dest"
    dest.mkdir()
    
    mock_monitor = MagicMock()
    mock_monitor_class.return_value.__enter__.return_value = mock_monitor
    
    # Mock run to exit immediately
    mock_monitor.run.side_effect = None 
    
    result = runner.invoke(app, ["watch", "--source", str(source), "--dest", str(dest)])
    
    assert result.exit_code == 0
    mock_write_pid.assert_called_once_with("watch", "copy-that watch")
    mock_monitor.watch_files.assert_called_once()
    mock_remove_pid.assert_called_once_with("watch")

@patch("copy_that.main.setup_logging")
@patch("copy_that.main.Monitor")
@patch("copy_that.main.is_process_running")
def test_watch_command_already_running(mock_is_running, mock_monitor_class, mock_setup_logging, tmp_path, caplog):
    mock_is_running.return_value = True
    source = tmp_path / "src"
    source.mkdir()
    
    with caplog.at_level(logging.ERROR):
        result = runner.invoke(app, ["watch", "--source", str(source), "--dest", str(tmp_path / "dest")])
    
    assert result.exit_code == 1
    assert "Error: A watch process is already running" in caplog.text

@patch("copy_that.main.Monitor")
@patch("copy_that.main.write_pid_file")
@patch("copy_that.main.remove_pid_file")
@patch("copy_that.main.is_process_running")
def test_auto_mount_command_basic(mock_is_running, mock_remove_pid, mock_write_pid, mock_monitor_class, tmp_path):
    mock_is_running.return_value = False
    dest = tmp_path / "dest"
    dest.mkdir()
    
    mock_monitor = MagicMock()
    mock_monitor_class.return_value.__enter__.return_value = mock_monitor
    
    result = runner.invoke(app, ["auto-mount", "--dest", str(dest)])
    
    assert result.exit_code == 0
    mock_write_pid.assert_called_once_with("auto-mount", "copy-that auto-mount")
    mock_monitor.watch_mounts.assert_called_once()
    mock_remove_pid.assert_called_once_with("auto-mount")

@patch("copy_that.lifecycle.psutil.Process")
def test_lifecycle_pid_management(mock_process_class, tmp_path):
    from copy_that.lifecycle import write_pid_file, is_process_running, remove_pid_file
    
    mock_proc = MagicMock()
    mock_proc.create_time.return_value = 12345.678
    mock_process_class.return_value = mock_proc
    
    with patch("os.getpid", return_value=9999):
        write_pid_file("test", "test-cmd")
    
    # Path.home() is mocked by fixture in conftest.py
    expected_path = Path.home() / ".config" / "copy-that" / "test.pid"
    assert expected_path.exists()
    
    with open(expected_path, "r") as f:
        data = json.load(f)
    assert data["pid"] == 9999
    assert data["started_at"] == 12345.678
    
    # Test is_process_running
    with patch("psutil.pid_exists", return_value=True):
        with patch("psutil.Process") as mock_p_class:
            mock_p = MagicMock()
            mock_p.create_time.return_value = 12345.678
            mock_p_class.return_value = mock_p
            assert is_process_running("test") == 9999
            
    remove_pid_file("test")
    assert not expected_path.exists()
