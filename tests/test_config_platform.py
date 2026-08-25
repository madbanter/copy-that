import sys
import os
import pytest
from pathlib import Path
from copy_that.config import get_default_log_file

def test_get_default_log_file_darwin(monkeypatch):
    mock_home = Path("/Users/mockuser")
    monkeypatch.setattr(Path, "home", lambda: mock_home)
    monkeypatch.setattr(sys, "platform", "darwin")
    path = get_default_log_file()
    assert str(path) == "/Users/mockuser/Library/Logs/copy-that/sync.log"

def test_get_default_log_file_linux_xdg(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setenv("XDG_STATE_HOME", "/tmp/xdg_state")
    path = get_default_log_file()
    assert str(path) == "/tmp/xdg_state/copy-that/sync.log"

def test_get_default_log_file_linux_default(monkeypatch):
    mock_home = Path("/home/mockuser")
    monkeypatch.setattr(Path, "home", lambda: mock_home)
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.delenv("XDG_STATE_HOME", raising=False)
    path = get_default_log_file()
    assert str(path) == "/home/mockuser/.local/state/copy-that/sync.log"

def test_get_default_log_file_other(monkeypatch):
    mock_home = Path("/home/mockuser")
    monkeypatch.setattr(Path, "home", lambda: mock_home)
    monkeypatch.setattr(sys, "platform", "win32")
    path = get_default_log_file()
    assert str(path) == "/home/mockuser/.copy-that/sync.log"

from copy_that.config import Config

def test_auto_mount_points_darwin(monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    c = Config(destination_base=Path("/tmp"))
    assert c.auto_mount_points == [Path("/Volumes")]

def test_auto_mount_points_linux(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    c = Config(destination_base=Path("/tmp"))
    assert c.auto_mount_points == [Path("/media")]

def test_auto_mount_points_win32(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    c = Config(destination_base=Path("/tmp"))
    assert c.auto_mount_points == []
