import pytest
import shutil
from pathlib import Path
from copy_that.main import perform_space_check, main
from copy_that.config import Config

def test_perform_space_check_sufficient(tmp_path, monkeypatch):
    source_file = tmp_path / "source.txt"
    source_file.write_text("hello")
    
    config = Config(
        source_directory=tmp_path,
        destination_base=tmp_path / "dest"
    )
    
    # Mock disk_usage to return plenty of space
    # shutil.usage returns (total, used, free)
    monkeypatch.setattr(shutil, "disk_usage", lambda p: shutil._ntuple_diskusage(1000, 500, 500))
    
    # Should not raise any warnings (we'd need to mock logger to be sure, 
    # but this at least ensures it doesn't crash)
    perform_space_check([source_file], config)

def test_perform_space_check_insufficient(tmp_path, monkeypatch, caplog):
    source_file = tmp_path / "source.txt"
    source_file.write_text("hello world") # 11 bytes
    
    config = Config(
        source_directory=tmp_path,
        destination_base=tmp_path / "dest"
    )
    
    # Mock disk_usage to return very little space (5 bytes)
    monkeypatch.setattr(shutil, "disk_usage", lambda p: shutil._ntuple_diskusage(100, 95, 5))
    
    with caplog.at_level("WARNING"):
        perform_space_check([source_file], config)
    
    assert "Possible insufficient disk space!" in caplog.text

def test_perform_space_check_skip_existing(tmp_path, monkeypatch, caplog):
    source_file = tmp_path / "source.txt"
    source_file.write_text("large file content")
    
    # Create the "already exists" file in destination
    # We need to know where it would be placed. 
    # generate_destination_path uses date by default.
    from copy_that.organizer import generate_destination_path
    dest_base = tmp_path / "dest"
    config = Config(
        source_directory=tmp_path,
        destination_base=dest_base,
        conflict_policy="skip"
    )
    
    dest_file = generate_destination_path(
        source_file, 
        config.source_directory,
        dest_base, 
        config.folder_format,
        config.organization_mode,
        config.date_source
    )
    dest_file.parent.mkdir(parents=True, exist_ok=True)
    dest_file.write_text("existing content")
    
    # Mock disk_usage to return 0 free space
    monkeypatch.setattr(shutil, "disk_usage", lambda p: shutil._ntuple_diskusage(100, 100, 0))
    
    # Should NOT warn because the file exists and policy is 'skip'
    with caplog.at_level("WARNING"):
        perform_space_check([source_file], config)
    
    assert "Possible insufficient disk space!" not in caplog.text

def test_dry_run_no_io(tmp_path, monkeypatch, caplog):
    source_dir = tmp_path / "src"
    source_dir.mkdir()
    (source_dir / "test.jpg").write_text("data")
    
    dest_dir = tmp_path / "dest"
    
    config_file = tmp_path / "config.yaml"
    config_file.write_text(f"""
source_directory: {source_dir}
destination_base: {dest_dir}
""")
    
    # Mock copy_file to ensure it's NOT called
    def error_if_called(*args, **kwargs):
        pytest.fail("copy_file should not be called during dry run")
    
    import copy_that.main
    monkeypatch.setattr(copy_that.main, "copy_file", error_if_called)
    
    # Mock sys.argv
    monkeypatch.setattr("sys.argv", ["copy-that", "--config", str(config_file), "--dry-run"])
    
    with caplog.at_level("INFO"):
        main()
        
    assert "[DRY RUN] Would copy" in caplog.text
    assert not dest_dir.exists()
