import pytest
from pathlib import Path
from copy_that.lifecycle import GracefulShutdown, ProcessLock

def test_process_lock(tmp_path, monkeypatch):
    # Mock home
    mock_home = tmp_path / "home"
    mock_home.mkdir()
    monkeypatch.setenv("HOME", str(mock_home))
    
    lock1 = ProcessLock("test")
    assert lock1.acquire() is True
    
    lock2 = ProcessLock("test")
    assert lock2.acquire() is False
    
    lock1.release()
    assert lock2.acquire() is True
    lock2.release()

def test_graceful_shutdown():
    shutdown = GracefulShutdown()
    assert shutdown.shutdown_requested is False
    # Manually trigger signal handler
    shutdown._handle_signal(15, None) # SIGTERM
    assert shutdown.shutdown_requested is True
