import pytest
from pathlib import Path
from unittest.mock import patch
from copy_that.config import find_config, merge_config

def test_find_config_local_priority(tmp_path, monkeypatch):
    """Test that local config.yaml takes precedence over config.yml."""
    local_yaml = tmp_path / "config.yaml"
    local_yml = tmp_path / "config.yml"
    
    local_yaml.write_text("source_directory: /tmp/yaml\ndestination_base: /tmp/dest")
    local_yml.write_text("source_directory: /tmp/yml\ndestination_base: /tmp/dest")
    
    monkeypatch.chdir(tmp_path)
    
    found = find_config()
    assert found == local_yaml.resolve()
    # Ultra-safety: Ensure we didn't leak out of tmp_path
    assert str(tmp_path) in str(found)
    
    local_yaml.unlink()
    found = find_config()
    assert found == local_yml.resolve()

def test_find_config_user_home_fallback(tmp_path, monkeypatch):
    """Test fallback to ~/.copy-that.yaml when no local config exists."""
    # Create a mock home directory
    mock_home = tmp_path / "home"
    mock_home.mkdir()
    user_config = mock_home / ".copy-that.yaml"
    user_config.write_text("source_directory: /tmp/home\ndestination_base: /tmp/dest")
    
    # Mock HOME environment variable
    monkeypatch.setenv("HOME", str(mock_home))
    
    # Move to a directory with no local config
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    monkeypatch.chdir(empty_dir)
    
    found = find_config()
    assert found is not None
    assert found.resolve() == user_config.resolve()

def test_find_config_xdg_fallback(tmp_path, monkeypatch):
    """Test fallback to ~/.config/copy-that/config.yaml."""
    mock_home = tmp_path / "home"
    mock_home.mkdir()
    xdg_config_dir = mock_home / ".config" / "copy-that"
    xdg_config_dir.mkdir(parents=True)
    xdg_config = xdg_config_dir / "config.yaml"
    xdg_config.write_text("source_directory: /tmp/xdg\ndestination_base: /tmp/dest")
    
    monkeypatch.setenv("HOME", str(mock_home))
    
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    monkeypatch.chdir(empty_dir)
    
    found = find_config()
    assert found is not None
    assert found.resolve() == xdg_config.resolve()

def test_merge_config_finds_local_automatically(tmp_path, monkeypatch):
    """Test that merge_config automatically finds local config when path is None."""
    local_config = tmp_path / "config.yaml"
    local_config.write_text("source_directory: /tmp/auto\ndestination_base: /tmp/dest")
    
    monkeypatch.chdir(tmp_path)
    
    # Passing no config_path should trigger find_config()
    config = merge_config()
    assert config.source_directory == Path("/tmp/auto").resolve()

def test_merge_config_explicit_path_not_found(tmp_path):
    """Test that providing an explicit path that doesn't exist raises FileNotFoundError."""
    with pytest.raises(FileNotFoundError, match="Explicitly provided configuration file not found"):
        merge_config(config_path=tmp_path / "nonexistent.yaml")

def test_merge_config_malformed_yaml(tmp_path):
    """Test that malformed YAML in a found config raises a helpful error."""
    bad_config = tmp_path / "config.yaml"
    bad_config.write_text("source_directory: [unclosed list")
    
    import yaml
    with pytest.raises(ValueError, match="Error parsing configuration file"):
        with patch("copy_that.config.find_config", return_value=bad_config):
            merge_config()

def test_merge_config_permission_error(tmp_path):
    """Test that PermissionError when reading a found config raises a helpful OSError."""
    locked_config = tmp_path / "config.yaml"
    locked_config.write_text("source_directory: /tmp/src")
    
    with patch("copy_that.config.find_config", return_value=locked_config):
        # Mock open to raise PermissionError
        with patch("builtins.open", side_effect=PermissionError("Permission denied")):
            with pytest.raises(OSError, match="Could not read configuration file"):
                merge_config()

def test_merge_config_empty_file(tmp_path):
    """Test that an empty configuration file is handled gracefully."""
    empty_config = tmp_path / "config.yaml"
    empty_config.write_text("") # Empty file
    
    with patch("copy_that.config.find_config", return_value=empty_config):
        # Should not crash, just return defaults or rely on CLI
        config = merge_config(source_directory=Path("/tmp/src"), destination_base=Path("/tmp/dest"))
        assert config.source_directory == Path("/tmp/src").resolve()

def test_find_config_search_error_handling(tmp_path):
    """Test that find_config skips paths that raise PermissionError or OSError."""
    # Mock a path that raises an error when resolved or checked for existence
    with patch("pathlib.Path.resolve", side_effect=PermissionError("Search restricted")):
        # Should return None instead of crashing
        assert find_config() is None

def test_merge_config_relative_path_resolution(tmp_path):
    """Test that relative paths in YAML are resolved relative to the config file location."""
    config_dir = tmp_path / "config_dir"
    config_dir.mkdir()
    config_file = config_dir / "config.yaml"
    
    # These paths are relative to the config file
    config_file.write_text("""
source_directory: "./input"
destination_base: "../output"
""")
    
    config = merge_config(config_path=config_file)
    
    # ./input -> config_dir/input
    assert config.source_directory == (config_dir / "input").resolve()
    # ../output -> tmp_path/output
    assert config.destination_base == (tmp_path / "output").resolve()

def test_merge_config_missing_required_fields_no_file():
    """Test error message when no config file exists and required fields are missing."""
    with patch("copy_that.config.find_config", return_value=None):
        with pytest.raises(ValueError, match="No configuration file found and required arguments are missing: source_directory, destination_base"):
            merge_config()

def test_merge_config_incomplete_file(tmp_path):
    """Test error message when a config file is found but is missing required fields."""
    incomplete_config = tmp_path / "config.yaml"
    incomplete_config.write_text("source_directory: /tmp/src") # Missing destination_base
    
    with patch("copy_that.config.find_config", return_value=incomplete_config):
        with pytest.raises(ValueError, match=f"Configuration from {incomplete_config.resolve()} is missing required fields: destination_base"):
            merge_config()

def test_merge_config_invalid_value():
    """Test error message for invalid configuration value (not just missing)."""
    # max_workers should be an integer
    with pytest.raises(ValueError, match="Invalid configuration:"):
        merge_config(source_directory=Path("/tmp/src"), destination_base=Path("/tmp/dest"), max_workers="lots")
