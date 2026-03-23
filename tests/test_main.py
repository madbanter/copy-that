import pytest
import shutil
import datetime
from pathlib import Path
from unittest.mock import patch
from copy_that.main import perform_space_check, main
from copy_that.config import Config

@pytest.fixture(autouse=True)
def mock_no_found_config():
    """Ensure tests don't accidentally pick up local config.yaml files."""
    with patch("copy_that.config.find_config", return_value=None):
        yield

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

def test_dry_run_no_io(tmp_path, monkeypatch, capsys):
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
    
    with pytest.raises(SystemExit) as e:
        main()
    assert e.value.code == 0
    
    captured = capsys.readouterr()
    assert "[DRY RUN] Copy" in captured.err
    assert not dest_dir.exists()

def test_cli_overrides(tmp_path, monkeypatch, capsys):
    source_dir = tmp_path / "src"
    source_dir.mkdir()
    (source_dir / "test.jpg").write_text("data")
    
    dest_dir = tmp_path / "dest"
    
    # We won't use a config file, just CLI overrides
    import copy_that.main
    monkeypatch.setattr("sys.argv", [
        "copy-that", 
        "--source", str(source_dir), 
        "--dest", str(dest_dir), 
        "--mode", "mirror",
        "--dry-run"
    ])
    
    with pytest.raises(SystemExit) as e:
        copy_that.main.main()
    assert e.value.code == 0
    
    captured = capsys.readouterr()
    assert f"Source: {source_dir.resolve()}" in captured.err
    assert f"Destination: {dest_dir.resolve()}" in captured.err
    assert "Mode: mirror" in captured.err
    assert "[DRY RUN] Copy" in captured.err

def test_main_source_not_exists(tmp_path, monkeypatch, capsys):
    # Mock sys.argv to point to a non-existent source
    monkeypatch.setattr("sys.argv", [
        "copy-that", 
        "--source", str(tmp_path / "nonexistent"), 
        "--dest", str(tmp_path / "dest"),
        "--dry-run"
    ])
    
    with pytest.raises(SystemExit) as e:
        main()
    assert e.value.code == 1
    
    captured = capsys.readouterr()
    assert "Source directory does not exist" in captured.err

def test_main_config_error(tmp_path, monkeypatch, capsys):
    # Mock sys.argv to point to an invalid config
    config_file = tmp_path / "invalid_config.yaml"
    config_file.write_text("source_directory: []") # Should fail pydantic validation
    
    monkeypatch.setattr("sys.argv", [
        "copy-that", 
        "--config", str(config_file)
    ])
    
    with pytest.raises(SystemExit) as e:
        main()
    assert e.value.code == 1
    
    captured = capsys.readouterr()
    assert "Configuration error" in captured.err

def test_main_corrupt_yaml(tmp_path, monkeypatch, capsys):
    # Mock sys.argv to point to a corrupt YAML config
    config_file = tmp_path / "corrupt_config.yaml"
    config_file.write_text("source_directory: [unclosed list")
    
    monkeypatch.setattr("sys.argv", [
        "copy-that", 
        "--config", str(config_file)
    ])
    
    with pytest.raises(SystemExit) as e:
        main()
    assert e.value.code == 1
    
    captured = capsys.readouterr()
    assert "Configuration error: Error parsing configuration file" in captured.err

def test_main_real_sync(tmp_path, monkeypatch, capsys):
    # Setup real source and destination
    source_dir = tmp_path / "src"
    source_dir.mkdir()
    (source_dir / "photo.jpg").write_text("image data content")
    
    dest_dir = tmp_path / "dest"
    
    # Run real sync using mirror mode
    monkeypatch.setattr("sys.argv", [
        "copy-that", 
        "--source", str(source_dir), 
        "--dest", str(dest_dir),
        "--mode", "mirror",
        "--no-space-check"
    ])
    
    with pytest.raises(SystemExit) as e:
        main()
    assert e.value.code == 0
    
    # Verify file was actually copied
    expected_file = dest_dir / "photo.jpg"
    assert expected_file.exists()
    assert expected_file.read_text() == "image data content"
    
    captured = capsys.readouterr()
    assert "Sync complete" in captured.err

def test_main_space_check_triggered(tmp_path, monkeypatch, capsys):
    source_dir = tmp_path / "src"
    source_dir.mkdir()
    (source_dir / "test.jpg").write_text("data")
    
    dest_dir = tmp_path / "dest"
    
    # Mock disk_usage to trigger a warning
    monkeypatch.setattr(shutil, "disk_usage", lambda p: shutil._ntuple_diskusage(100, 99, 1))
    
    monkeypatch.setattr("sys.argv", [
        "copy-that",
        "--source", str(source_dir),
        "--dest", str(dest_dir),
        "--space-check",
        "--dry-run"
    ])
    
    with pytest.raises(SystemExit) as e:
        main()
    assert e.value.code == 0
    
    captured = capsys.readouterr()
    assert "Performing pre-sync disk space check" in captured.err
    assert "Possible insufficient disk space!" in captured.err

def test_main_filename_date_dry_run(tmp_path, monkeypatch, capsys):
    source_dir = tmp_path / "src"
    source_dir.mkdir()
    filename = "2023-01-01 12.00.00.jpg"
    (source_dir / filename).write_text("data")
    
    dest_dir = tmp_path / "dest"
    
    monkeypatch.setattr("sys.argv", [
        "copy-that",
        "--source", str(source_dir),
        "--dest", str(dest_dir),
        "--date-source", "filename",
        "--dry-run"
    ])
    
    with pytest.raises(SystemExit) as e:
        main()
    assert e.value.code == 0
    
    captured = capsys.readouterr()
    # Default folder_format is %Y%m%d. Logger output includes 'dest/' prefix because it's relative to dest.parent
    assert f"[DRY RUN] Copy: {filename} -> dest/20230101/{filename}" in captured.err

def test_main_filename_date_space_check(tmp_path, monkeypatch, capsys):
    source_dir = tmp_path / "src"
    source_dir.mkdir()
    filename = "2023-01-01 12.00.00.jpg"
    (source_dir / filename).write_text("data")
    
    dest_dir = tmp_path / "dest"
    
    # Mock disk_usage to return 0 space to trigger warning
    monkeypatch.setattr(shutil, "disk_usage", lambda p: shutil._ntuple_diskusage(100, 100, 0))
    
    monkeypatch.setattr("sys.argv", [
        "copy-that",
        "--source", str(source_dir),
        "--dest", str(dest_dir),
        "--date-source", "filename",
        "--space-check",
        "--dry-run"
    ])
    
    with pytest.raises(SystemExit) as e:
        main()
    assert e.value.code == 0
    
    captured = capsys.readouterr()
    assert "Performing pre-sync disk space check" in captured.err
    assert "Possible insufficient disk space!" in captured.err

def test_cli_filename_date_source(tmp_path, monkeypatch, capsys):
    source_dir = tmp_path / "src"
    source_dir.mkdir()
    # Create file with date in name
    filename = "2015-12-26 15.13.52-1.jpg"
    (source_dir / filename).write_text("data")
    
    dest_dir = tmp_path / "dest"
    
    # Run sync with filename date source
    monkeypatch.setattr("sys.argv", [
        "copy-that", 
        "--source", str(source_dir), 
        "--dest", str(dest_dir),
        "--date-source", "filename",
        "--filename-date-format", "%Y-%m-%d %H.%M.%S",
        "--format", "%Y-%m-%d",
        "--no-space-check"
    ])
    
    with pytest.raises(SystemExit) as e:
        main()
    assert e.value.code == 0
    
    # Verify file was copied to the correct date-based folder
    expected_file = dest_dir / "2015-12-26" / filename
    assert expected_file.exists()
    assert expected_file.read_text() == "data"
    
    captured = capsys.readouterr()
    assert "Sync complete" in captured.err

def test_integrity_aware_skip_dry_run(tmp_path, monkeypatch, capsys):
    today = datetime.datetime.now().strftime("%Y%m%d")
    source_dir = tmp_path / "src"
    source_dir.mkdir()
    (source_dir / "test.jpg").write_text("source data")
    
    dest_dir = tmp_path / "dest"
    dest_dir.mkdir()
    # Create an identical file in destination
    (dest_dir / today).mkdir()
    (dest_dir / today / "test.jpg").write_text("source data")
    
    # Run dry run with verification
    monkeypatch.setattr("sys.argv", [
        "copy-that",
        "--source", str(source_dir),
        "--dest", str(dest_dir),
        "--verify", "size",
        "--dry-run"
    ])
    
    with pytest.raises(SystemExit) as e:
        main()
    assert e.value.code == 0
    
    captured = capsys.readouterr()
    assert "[DRY RUN] Skip (already verified)" in captured.err

    # Now modify the destination to fail verification
    (dest_dir / today / "test.jpg").write_text("different")
    
    with pytest.raises(SystemExit) as e:
        main()
    assert e.value.code == 0
    
    captured = capsys.readouterr()
    assert "[DRY RUN] Overwrite (failed verification)" in captured.err

def test_dry_run_rename_policy(tmp_path, monkeypatch, capsys):
    today = datetime.datetime.now().strftime("%Y%m%d")
    source_dir = tmp_path / "src"
    source_dir.mkdir()
    (source_dir / "test.jpg").write_text("data")
    
    dest_dir = tmp_path / "dest"
    dest_dir.mkdir()
    (dest_dir / today).mkdir()
    (dest_dir / today / "test.jpg").write_text("old")
    
    monkeypatch.setattr("sys.argv", [
        "copy-that",
        "--source", str(source_dir),
        "--dest", str(dest_dir),
        "--conflict", "rename",
        "--dry-run"
    ])
    
    with pytest.raises(SystemExit) as e:
        main()
    assert e.value.code == 0
    
    captured = capsys.readouterr()
    assert "[DRY RUN] Rename to test_1.jpg" in captured.err

def test_smart_sync_concurrency(tmp_path, monkeypatch, capsys):
    today = datetime.datetime.now().strftime("%Y%m%d")
    # Stress test with multiple files and workers
    source_dir = tmp_path / "src"
    source_dir.mkdir()
    dest_dir = tmp_path / "dest"
    dest_dir.mkdir()
    
    num_files = 20
    for i in range(num_files):
        # Half identical, half different
        content = f"content {i}"
        source_file = source_dir / f"file_{i}.txt"
        source_file.write_text(content)
        
        if i % 2 == 0: # Even index files are identical
            dest_subdir = dest_dir / today
            dest_subdir.mkdir(exist_ok=True)
            dest_file = dest_subdir / f"file_{i}.txt"
            dest_file.write_text(content) # Identical
        else: # Odd index files are different
            dest_subdir = dest_dir / today
            dest_subdir.mkdir(exist_ok=True)
            dest_file = dest_subdir / f"file_{i}.txt"
            dest_file.write_text("corrupt") # Different
            
    monkeypatch.setattr("sys.argv", [
        "copy-that",
        "--source", str(source_dir),
        "--dest", str(dest_dir),
        "--verify", "size",
        "--workers", "4",
        "--ext", ".txt"  # Explicitly include .txt files for this test
    ])
    
    with pytest.raises(SystemExit) as e:
        main()
    assert e.value.code == 0
    
    # 10 should be copied (the 'corrupt' ones), 10 should be skipped (the verified ones)
    captured = capsys.readouterr()
    assert "Processed 20 files, copied 10" in captured.err
