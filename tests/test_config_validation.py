import pytest
from pathlib import Path
from pydantic import ValidationError
from copy_that.config import Config

def test_config_buffer_size_validation():
    # Valid min/max
    Config(source_directory=Path("."), destination_base=Path("."), buffer_size=1024)
    Config(source_directory=Path("."), destination_base=Path("."), buffer_size=128 * 1024 * 1024)
    
    # Invalid too small
    with pytest.raises(ValidationError):
        Config(source_directory=Path("."), destination_base=Path("."), buffer_size=1023)
        
    # Invalid too large
    with pytest.raises(ValidationError):
        Config(source_directory=Path("."), destination_base=Path("."), buffer_size=128 * 1024 * 1024 + 1)

def test_config_retry_validation():
    # Valid
    Config(source_directory=Path("."), destination_base=Path("."), max_retries=0)
    Config(source_directory=Path("."), destination_base=Path("."), retry_base_delay=0.0)
    
    # Invalid negative
    with pytest.raises(ValidationError):
        Config(source_directory=Path("."), destination_base=Path("."), max_retries=-1)
        
    with pytest.raises(ValidationError):
        Config(source_directory=Path("."), destination_base=Path("."), retry_base_delay=-0.5)

def test_config_path_expansion_after_validation(tmp_path):
    # Ensure relative paths are resolved even when using constructor directly
    source = tmp_path / "src"
    source.mkdir()
    
    config = Config(source_directory=source, destination_base=Path("."))
    assert config.source_directory.is_absolute()
    assert config.destination_base.is_absolute()
