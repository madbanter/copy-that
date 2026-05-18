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
