import pytest
import time
import os
import signal
import psutil
import json
from pathlib import Path
from unittest.mock import MagicMock, patch
from copy_that.lifecycle import GracefulShutdown, write_pid_file, is_process_running, remove_pid_file, stop_process

def test_graceful_shutdown_signals():
    gs = GracefulShutdown()
    assert gs.shutdown_requested is False
    
    # Simulate signal
    gs._handle_signal(signal.SIGINT, None)
    assert gs.shutdown_requested is True

def test_pid_lifecycle(tmp_path, monkeypatch):
    # Setup mock home
    mock_home = tmp_path / "home"
    mock_home.mkdir()
    monkeypatch.setenv("HOME", str(mock_home))
    
    # Mock psutil.Process.create_time to avoid real process lookup issues
    with patch("psutil.Process") as mock_proc_class:
        mock_proc = MagicMock()
        mock_proc.create_time.return_value = 100.0
        mock_proc_class.return_value = mock_proc
        
        # Test write
        write_pid_file("test", "cmd")
        pid_file = Path.home() / ".config" / "copy-that" / "test.pid"
        assert pid_file.exists()
        
        # Test stale check
        with patch("psutil.pid_exists", return_value=True):
            assert is_process_running("test") == os.getpid()
            
        # Test stale PID (create time mismatch)
        mock_proc.create_time.return_value = 200.0
        assert is_process_running("test") is None
        assert not pid_file.exists()

def test_stop_process_nonexistent():
    assert stop_process("nonexistent") is False
