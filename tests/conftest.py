import logging
import pytest

@pytest.fixture(autouse=True)
def restore_logging():
    """
    Ensure logging handlers are restored after each test.
    This prevents any test calling main() from breaking pytest's caplog/output
    for subsequent tests.
    """
    root_logger = logging.getLogger()
    # Store original state
    original_handlers = root_logger.handlers[:]
    original_level = root_logger.level
    
    yield
    
    # Restore state
    # 1. Close and remove any handlers added during the test
    for handler in root_logger.handlers[:]:
        if handler not in original_handlers:
            root_logger.removeHandler(handler)
            if hasattr(handler, "close"):
                handler.close()
    
    # 2. Ensure all original handlers are still there
    for handler in original_handlers:
        if handler not in root_logger.handlers:
            root_logger.addHandler(handler)
            
    root_logger.setLevel(original_level)
