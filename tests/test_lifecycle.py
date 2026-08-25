import pytest
import os
import signal
from pathlib import Path
from unittest.mock import patch
from copy_that.lifecycle import GracefulShutdown, ProcessLock, stop_process, get_lock_file

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


def test_stop_process_no_lock_file(tmp_path, monkeypatch):
    """stop_process returns False immediately when no lock file exists."""
    monkeypatch.setenv("HOME", str(tmp_path))
    assert stop_process("nonexistent-service") is False


def test_stop_process_sends_sigterm(tmp_path, monkeypatch):
    """stop_process reads PID from lock file and sends SIGTERM; returns True."""
    monkeypatch.setenv("HOME", str(tmp_path))
    lock = ProcessLock("test-svc")
    lock.acquire()

    signals_sent = []
    def mock_kill(pid, sig):
        signals_sent.append((pid, sig))

    with patch("os.kill", side_effect=mock_kill):
        result = stop_process("test-svc")

    assert result is True
    assert signals_sent == [(os.getpid(), signal.SIGTERM)]
    lock.release()


def test_stop_process_process_lookup_error(tmp_path, monkeypatch):
    """stop_process returns False when the PID no longer exists."""
    monkeypatch.setenv("HOME", str(tmp_path))
    lock = ProcessLock("dead-svc")
    lock.acquire()
    lock._pid_file.write_text("99999999")

    with patch("os.kill", side_effect=ProcessLookupError):
        result = stop_process("dead-svc")

    assert result is False
    lock.release()


def test_stop_process_corrupt_pid_file(tmp_path, monkeypatch):
    """stop_process returns False when the lock file contains non-integer data."""
    monkeypatch.setenv("HOME", str(tmp_path))
    lock = ProcessLock("corrupt-svc")
    lock.acquire()
    lock._pid_file.write_text("not-a-pid")

    result = stop_process("corrupt-svc")
    assert result is False
    lock.release()

