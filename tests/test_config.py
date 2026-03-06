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

def test_home_expansion():
    # Pydantic should expand ~ to the actual home directory
    config = Config(
        source_directory=Path("~/src"),
        destination_base=Path("~/dest")
    )
    assert config.source_directory == Path.home() / "src"
    assert config.destination_base == Path.home() / "dest"

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

def test_extension_normalization():
    config = Config(
        source_directory=Path("/tmp/src"),
        destination_base=Path("/tmp/dest"),
        include_extensions=["JPG", ".PNG", "mp4", ".ARW"]
    )
    assert config.include_extensions == [".jpg", ".png", ".mp4", ".arw"]
