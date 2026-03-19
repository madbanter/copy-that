import pytest
from pathlib import Path
from unittest.mock import patch
from copy_that.config import Config, merge_config

@pytest.fixture(autouse=True)
def mock_no_found_config():
    """Ensure tests don't accidentally pick up local config.yaml files."""
    with patch("copy_that.config.find_config", return_value=None):
        yield

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

def test_home_expansion(tmp_path, monkeypatch):
    # Mock HOME to ensure test is environment-agnostic
    mock_home = tmp_path / "fake_home"
    mock_home.mkdir()
    monkeypatch.setenv("HOME", str(mock_home))
    
    config = Config(
        source_directory=Path("~/src"),
        destination_base=Path("~/dest")
    )
    assert config.source_directory == mock_home / "src"
    assert config.destination_base == mock_home / "dest"

def test_extension_normalization():
    config = Config(
        source_directory=Path("/tmp/src"),
        destination_base=Path("/tmp/dest"),
        include_extensions=["JPG", ".PNG", "mp4", ".ARW"]
    )
    assert config.include_extensions == [".jpg", ".png", ".mp4", ".arw"]

def test_merge_config_no_file(tmp_path):
    # Test merging when no config file exists, only CLI args
    source = tmp_path / "src"
    dest = tmp_path / "dest"
    source.mkdir()
    dest.mkdir()
    
    # Passing None for config_path triggers the search (which will find nothing)
    # instead of passing a non-existent path which now raises an error.
    config = merge_config(
        config_path=None,
        source_directory=source,
        destination_base=dest,
        organization_mode="mirror"
    )
    
    assert config.source_directory == source.resolve()
    assert config.destination_base == dest.resolve()
    assert config.organization_mode == "mirror"
    # Defaults should still be present
    assert config.conflict_policy == "skip"

def test_merge_config_with_file_overrides(tmp_path):
    # Test CLI args overriding YAML file
    config_file = tmp_path / "config.yaml"
    config_file.write_text("""
source_directory: "/tmp/yaml_src"
destination_base: "/tmp/yaml_dest"
organization_mode: "date"
""")
    
    source_override = tmp_path / "cli_src"
    source_override.mkdir()
    
    config = merge_config(
        config_path=config_file,
        source_directory=source_override,
        organization_mode="mirror"
    )
    
    # Overridden values
    assert config.source_directory == source_override.resolve()
    assert config.organization_mode == "mirror"
    # YAML value preserved if not overridden
    assert config.destination_base == Path("/tmp/yaml_dest").resolve()

def test_merge_config_none_values_ignored(tmp_path):
    # Test that passing None in kwargs doesn't overwrite YAML values
    config_file = tmp_path / "config.yaml"
    config_file.write_text("""
source_directory: "/tmp/yaml_src"
destination_base: "/tmp/yaml_dest"
""")
    
    config = merge_config(
        config_path=config_file,
        source_directory=None,  # Should be ignored
        destination_base=None   # Should be ignored
    )
    
    assert config.source_directory == Path("/tmp/yaml_src").resolve()
    assert config.destination_base == Path("/tmp/yaml_dest").resolve()
