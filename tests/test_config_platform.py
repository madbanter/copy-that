import sys
import os
import pytest
from pathlib import Path
from copy_that.config import get_default_log_file

def test_get_default_log_file_darwin(monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    path = get_default_log_file()
    assert "Library/Logs/copy-that/sync.log" in str(path)

def test_get_default_log_file_linux_xdg(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setenv("XDG_STATE_HOME", "/tmp/xdg_state")
    path = get_default_log_file()
    assert str(path) == "/tmp/xdg_state/copy-that/sync.log"

def test_get_default_log_file_linux_default(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.delenv("XDG_STATE_HOME", raising=False)
    path = get_default_log_file()
    assert ".local/state/copy-that/sync.log" in str(path)

def test_get_default_log_file_other(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    path = get_default_log_file()
    assert ".copy-that/sync.log" in str(path)
