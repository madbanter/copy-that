import pytest
from pathlib import Path
from copy_that.config import Config, load_config

def test_config_expansion(tmp_path):
    source = tmp_path / "source"
    dest = tmp_path / "dest"
    source.mkdir()
    dest.mkdir()
    
    config = Config(
        source_directory=source,
        destination_base=dest
    )
    
    assert config.source_directory == source.resolve()
    assert config.destination_base == dest.resolve()

def test_load_config_file(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text("""
source_directory: "/tmp/src"
destination_base: "/tmp/dest"
conflict_policy: "rename"
""")
    
    config = load_config(config_file)
    assert config.source_directory.name == "src"
    assert config.conflict_policy == "rename"
