import pytest
import logging
from unittest.mock import patch, MagicMock
from copy_that.main import app
from typer.testing import CliRunner
from pathlib import Path

runner = CliRunner()

@pytest.fixture
def mock_lock_dir(tmp_path, monkeypatch):
    """Ensure lock files are created in the temporary test directory."""
    lock_dir = tmp_path / ".config" / "copy-that"
    lock_dir.mkdir(parents=True)
    
    # Mock Path.home to return our tmp_path
    mock_home = tmp_path
    with patch("pathlib.Path.home", return_value=mock_home):
        yield lock_dir

def test_stop_command_no_args(caplog):
    with caplog.at_level(logging.INFO):
        result = runner.invoke(app, ["stop"])
    assert result.exit_code == 0
    assert "No active background processes to stop" in caplog.text

def test_watch_command_basic(tmp_path):
    source = tmp_path / "src"
    source.mkdir()
    dest = tmp_path / "dest"
    dest.mkdir()
    
    with patch("copy_that.main.Monitor") as mock_monitor_class:
        mock_monitor = MagicMock()
        mock_monitor_class.return_value.__enter__.return_value = mock_monitor
        
        result = runner.invoke(app, ["watch", "--source", str(source), "--dest", str(dest)])
    
    assert result.exit_code == 0
    mock_monitor.watch_files.assert_called_once()

@patch("copy_that.main.setup_logging")
@patch("copy_that.main.ProcessLock")
def test_watch_command_already_running(mock_lock_class, mock_setup_logging, tmp_path, caplog):
    mock_lock = MagicMock()
    mock_lock.acquire.return_value = False
    mock_lock_class.return_value = mock_lock

    source = tmp_path / "src"
    source.mkdir()

    with caplog.at_level(logging.ERROR):
        result = runner.invoke(app, ["watch", "--source", str(source), "--dest", str(tmp_path / "dest")])

    assert result.exit_code == 1
    assert "Error: A watch process is already running" in caplog.text

@patch("copy_that.main.Monitor")
def test_auto_mount_command_basic(mock_monitor_class, tmp_path):
    dest = tmp_path / "dest"
    dest.mkdir()

    mock_monitor = MagicMock()
    mock_monitor_class.return_value.__enter__.return_value = mock_monitor

    result = runner.invoke(app, ["auto-mount", "--dest", str(dest)])

    assert result.exit_code == 0
    mock_monitor.watch_mounts.assert_called_once()

@patch("copy_that.main.setup_logging")
@patch("copy_that.main.ProcessLock")
def test_auto_mount_already_running(mock_lock_class, mock_setup_logging, tmp_path, caplog):
    mock_lock = MagicMock()
    mock_lock.acquire.return_value = False
    mock_lock_class.return_value = mock_lock

    with caplog.at_level(logging.ERROR):
        result = runner.invoke(app, ["auto-mount", "--dest", str(tmp_path / "dest")])

    assert result.exit_code == 1
    assert "Error: An auto-mount process is already running" in caplog.text

