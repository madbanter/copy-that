import time
import pytest
from unittest.mock import MagicMock
from copy_that.monitor import SyncTrigger, MountMonitor
from pathlib import Path

def test_sync_trigger_debounce():
    triggered = False
    def callback():
        nonlocal triggered
        triggered = True
        
    trigger = SyncTrigger(callback, debounce_seconds=1.0)
    
    # First attempt: should trigger
    trigger.attempt_trigger("path1")
    assert triggered is True
    
    # Reset
    triggered = False
    
    # Second attempt (too soon): should NOT trigger
    trigger.attempt_trigger("path2")
    assert triggered is False
    
    # Third attempt (after debounce): should trigger
    time.sleep(1.1)
    trigger.attempt_trigger("path3")
    assert triggered is True

def test_mount_monitor_detection(tmp_path):
    # Mock mount points
    mp1 = tmp_path / "mnt1"
    mp1.mkdir()
    
    # Callback
    detected_mounts = []
    def on_mount(p):
        detected_mounts.append(p)
        
    monitor = MountMonitor([mp1], on_mount, [])
    
    # Simulate a new mount
    new_mount = mp1 / "drive1"
    new_mount.mkdir()
    
    monitor.check()
    assert len(detected_mounts) == 1
    assert detected_mounts[0] == new_mount
    
    # Second check (should not trigger again)
    monitor.check()
    assert len(detected_mounts) == 1


def test_watch_mounts_empty_list_warns(caplog):
    """watch_mounts with an empty list logs a warning and returns without scheduling."""
    import logging
    from unittest.mock import MagicMock, patch
    from copy_that.monitor import Monitor
    from copy_that.lifecycle import GracefulShutdown

    shutdown = GracefulShutdown()
    with patch("copy_that.monitor.Observer"):
        monitor = Monitor(shutdown)
        with caplog.at_level(logging.WARNING, logger="copy_that.monitor"):
            monitor.watch_mounts([], on_mount=MagicMock(), whitelist=[])

    assert "No mount points configured" in caplog.text


def test_watch_mounts_missing_path_warns(tmp_path, caplog):
    """watch_mounts skips and warns for mount points that do not exist on disk."""
    import logging
    from unittest.mock import MagicMock, patch
    from copy_that.monitor import Monitor
    from copy_that.lifecycle import GracefulShutdown

    existing = tmp_path / "real"
    existing.mkdir()
    missing = tmp_path / "ghost"  # intentionally not created

    shutdown = GracefulShutdown()
    with patch("copy_that.monitor.Observer") as mock_observer_cls:
        mock_observer = MagicMock()
        mock_observer_cls.return_value = mock_observer

        monitor = Monitor(shutdown)
        with caplog.at_level(logging.WARNING, logger="copy_that.monitor"):
            monitor.watch_mounts([existing, missing], on_mount=MagicMock(), whitelist=[])

    assert "does not exist" in caplog.text
    # Only the existing path should be scheduled
    assert mock_observer.schedule.call_count == 1
    scheduled_path = mock_observer.schedule.call_args[0][1]
    assert scheduled_path == str(existing)


def test_watch_mounts_multiple_valid_paths(tmp_path):
    """watch_mounts schedules observers for all valid mount points."""
    from unittest.mock import MagicMock, patch
    from copy_that.monitor import Monitor
    from copy_that.lifecycle import GracefulShutdown

    mp1 = tmp_path / "mnt1"
    mp1.mkdir()
    mp2 = tmp_path / "mnt2"
    mp2.mkdir()

    shutdown = GracefulShutdown()
    with patch("copy_that.monitor.Observer") as mock_observer_cls:
        mock_observer = MagicMock()
        mock_observer_cls.return_value = mock_observer

        monitor = Monitor(shutdown)
        monitor.watch_mounts([mp1, mp2], on_mount=MagicMock(), whitelist=[])

    assert mock_observer.schedule.call_count == 2
    scheduled_paths = {call[0][1] for call in mock_observer.schedule.call_args_list}
    assert str(mp1) in scheduled_paths
    assert str(mp2) in scheduled_paths

