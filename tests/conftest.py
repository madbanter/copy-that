import logging
import pytest
import os
from pathlib import Path
from unittest.mock import patch

@pytest.fixture(autouse=True)
def isolate_filesystem(tmp_path, monkeypatch):
    """
    Ensure tests don't touch the actual user's home or config directories.
    """
    # Create a unique fake home directory
    fake_home = tmp_path / "fake_home"
    # Use exist_ok just in case, though tmp_path should be unique per test
    fake_home.mkdir(parents=True, exist_ok=True)
    
    # Mock Path.home() globally
    with patch("pathlib.Path.home", return_value=fake_home):
        # Also set HOME env var for any code that uses os.environ
        monkeypatch.setenv("HOME", str(fake_home))
        # Ensure XDG_CONFIG_HOME is also mocked to avoid using real config paths
        monkeypatch.setenv("XDG_CONFIG_HOME", str(fake_home / ".config"))
        yield fake_home

@pytest.fixture
def mock_no_found_config():
    """
    Ensure tests don't accidentally pick up local config.yaml files.
    """
    with patch("copy_that.config.find_config", return_value=None):
        yield

@pytest.fixture(autouse=True)
def restore_logging():
    """
    Ensure logging handlers are restored after each test.
    This prevents any test calling main() from breaking pytest's caplog/output
    for subsequent tests.
    """
    root_logger = logging.getLogger()
    main_logger = logging.getLogger("copy_that")
    
    # Store original state
    original_root_handlers = root_logger.handlers[:]
    original_root_level = root_logger.level
    
    original_main_handlers = main_logger.handlers[:]
    original_main_level = main_logger.level
    original_main_propagate = main_logger.propagate
    
    yield
    
    # Restore root state
    for handler in root_logger.handlers[:]:
        if handler not in original_root_handlers:
            root_logger.removeHandler(handler)
            if hasattr(handler, "close"):
                handler.close()
    
    for handler in original_root_handlers:
        if handler not in root_logger.handlers:
            root_logger.addHandler(handler)
    root_logger.setLevel(original_root_level)

    # Restore copy_that state
    for handler in main_logger.handlers[:]:
        if handler not in original_main_handlers:
            main_logger.removeHandler(handler)
            if hasattr(handler, "close"):
                handler.close()
    
    for handler in original_main_handlers:
        if handler not in main_logger.handlers:
            main_logger.addHandler(handler)
            
    main_logger.setLevel(original_main_level)
    main_logger.propagate = original_main_propagate
