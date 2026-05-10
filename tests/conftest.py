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
