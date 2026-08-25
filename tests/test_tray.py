import sys
import threading
from pathlib import Path
from unittest.mock import patch, MagicMock
from copy_that.tray import TrayApp, is_daemon_running, get_tray_backend

def test_is_daemon_running_true(monkeypatch):
    mock_lock = MagicMock()
    # If acquire raises Timeout, daemon is running
    from filelock import Timeout
    mock_lock.acquire.side_effect = Timeout(lock_file="mock")
    
    with patch("copy_that.tray.FileLock", return_value=mock_lock):
        assert is_daemon_running() is True

def test_is_daemon_running_false(monkeypatch):
    mock_lock = MagicMock()
    # If acquire succeeds, daemon is not running
    mock_lock.acquire.return_value = None
    
    with patch("copy_that.tray.FileLock", return_value=mock_lock):
        assert is_daemon_running() is False

def test_tray_app_initialization(monkeypatch):
    # Mock threading to avoid background loop
    with patch("threading.Thread.start") as mock_start:
        with patch("copy_that.tray.get_tray_backend") as mock_backend:
            app = TrayApp()
            mock_backend.return_value.add_menu_item.assert_called()
            mock_start.assert_called_once()
            assert app._running is True

def test_tray_app_callbacks():
    with patch("threading.Thread.start"):
        with patch("copy_that.tray.get_tray_backend"):
            app = TrayApp()
            
            # Test quit
            app.quit()
            assert app._running is False
            app.backend.stop.assert_called_once()
            
            # Test stop_daemon
            with patch("copy_that.lifecycle.stop_process") as mock_stop:
                app.stop_daemon()
                mock_stop.assert_called_with("watcher")

def test_tray_app_start_daemon():
    with patch("threading.Thread.start"):
        with patch("copy_that.tray.get_tray_backend"):
            app = TrayApp()
            
            # Not frozen
            with patch("subprocess.Popen") as mock_popen:
                with patch("sys.executable", "python"):
                    app.start_daemon()
                    mock_popen.assert_called_with(["python", "-m", "copy_that.main"])
