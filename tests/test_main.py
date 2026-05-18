import pytest
import shutil
import datetime
import os
import logging
from pathlib import Path
from unittest.mock import patch
from copy_that.main import perform_space_check, main, SyncJob
from copy_that.config import Config

@pytest.fixture(autouse=True)
def mock_no_found_config():
    """Ensure tests don't accidentally pick up local config.yaml files."""
    with patch("copy_that.config.find_config", return_value=None):
        yield

def test_perform_space_check_sufficient(tmp_path, monkeypatch):
    source_file = tmp_path / "source.txt"
    source_file.write_text("hello")
    dest_file = tmp_path / "dest" / "source.txt"
    
    config = Config(
        source_directory=tmp_path,
        destination_base=tmp_path / "dest"
    )
    
    monkeypatch.setattr(shutil, "disk_usage", lambda p: shutil._ntuple_diskusage(1000, 500, 500))
    perform_space_check([SyncJob(source_file, dest_file, 5)], config)

def test_perform_space_check_insufficient(tmp_path, monkeypatch, caplog):
    source_file = tmp_path / "source.txt"
    source_file.write_text("hello world") # 11 bytes
    dest_file = tmp_path / "dest" / "source.txt"
    
    config = Config(
        source_directory=tmp_path,
        destination_base=tmp_path / "dest"
    )
    
    # Mock disk_usage to return very little space (5 bytes)
    monkeypatch.setattr(shutil, "disk_usage", lambda p: shutil._ntuple_diskusage(100, 95, 5))
    
    with caplog.at_level("WARNING"):
        perform_space_check([SyncJob(source_file, dest_file, 11)], config)
    
    assert "Possible insufficient disk space!" in caplog.text

def test_perform_space_check_skip_existing(tmp_path, monkeypatch, caplog):
    source_file = tmp_path / "source.txt"
    source_file.write_text("large file content")
    
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
        perform_space_check([SyncJob(source_file, dest_file, 100)], config)
    
    assert "Possible insufficient disk space!" not in caplog.text

def test_dry_run_no_io(tmp_path, monkeypatch, capsys):
    source_dir = tmp_path / "src"
    source_dir.mkdir()
    (source_dir / "test.jpg").write_text("data")
    dest_dir = tmp_path / "dest"
    dest_dir.mkdir()
    
    # Mock copy_file to ensure it's NOT called
    def error_if_called(*args, **kwargs):
        pytest.fail("copy_file should not be called during dry run")
    
    import copy_that.main
    monkeypatch.setattr(copy_that.main, "copy_file", error_if_called)
    
    monkeypatch.setattr("sys.argv", [
        "copy-that", 
        "sync",
        "--source", str(source_dir), 
        "--dest", str(dest_dir), 
        "--dry-run"
    ])
    
    with pytest.raises(SystemExit) as e:
        main()
    assert e.value.code == 0
    
    captured = capsys.readouterr()
    assert "Copied" in captured.err
    assert "test.jpg" in captured.err
    assert "Sync Summary (DRY RUN)" in captured.err

def test_cli_overrides(tmp_path, monkeypatch, capsys):
    source_dir = tmp_path / "src"
    source_dir.mkdir()
    (source_dir / "test.jpg").write_text("data")
    dest_dir = tmp_path / "dest"
    dest_dir.mkdir()
    
    monkeypatch.setattr("sys.argv", [
        "copy-that", 
        "sync",
        "--source", str(source_dir), 
        "--dest", str(dest_dir), 
        "--mode", "mirror",
        "--dry-run"
    ])
    
    with pytest.raises(SystemExit) as e:
        main()
    assert e.value.code == 0
    captured = capsys.readouterr()
    err_norm = " ".join(captured.err.split())
    assert "Sync Summary" in err_norm
    assert "DRY RUN" in err_norm
    assert "Source:" in err_norm
    assert "Destination:" in err_norm
    assert "Mode: mirror" in err_norm
    assert "would copy" in err_norm.lower()


def test_main_source_not_exists(tmp_path, monkeypatch, capsys):
    dest_dir = tmp_path / "dest"
    dest_dir.mkdir()
    
    monkeypatch.setattr("sys.argv", [
        "copy-that", 
        "sync",
        "--source", str(tmp_path / "nonexistent"), 
        "--dest", str(dest_dir),
        "--dry-run"
    ])
    
    with pytest.raises(SystemExit) as e:
        main()
    assert e.value.code == 1
    
    captured = capsys.readouterr()
    err_norm = " ".join(captured.err.split())
    assert "Source directory does not" in err_norm

def test_main_config_error(tmp_path, monkeypatch, caplog):
    config_file = tmp_path / "invalid_config.yaml"
    config_file.write_text("source_directory: []") 
    
    monkeypatch.setattr("sys.argv", [
        "copy-that", 
        "sync",
        "--config", str(config_file)
    ])
    
    with caplog.at_level(logging.ERROR):
        with pytest.raises(SystemExit) as e:
            main()
    assert e.value.code == 1
    assert "Configuration error" in caplog.text

def test_main_config_merge_error(tmp_path, monkeypatch, caplog):
    source_dir = tmp_path / "src"
    source_dir.mkdir()
    dest_dir = tmp_path / "dest"
    dest_dir.mkdir()
    
    with patch("copy_that.main.merge_config", side_effect=ValueError("Merge failed")):
        monkeypatch.setattr("sys.argv", ["copy-that", "sync", "--source", str(source_dir), "--dest", str(dest_dir)])
        with caplog.at_level(logging.ERROR):
            with pytest.raises(SystemExit) as e:
                main()
        assert e.value.code == 1
        assert "Merge failed" in caplog.text

def test_main_corrupt_yaml(tmp_path, monkeypatch, caplog):
    config_file = tmp_path / "corrupt_config.yaml"
    config_file.write_text("source_directory: [unclosed list")
    
    monkeypatch.setattr("sys.argv", [
        "copy-that", 
        "sync",
        "--config", str(config_file)
    ])
    
    with caplog.at_level(logging.ERROR):
        with pytest.raises(SystemExit) as e:
            main()
    assert e.value.code == 1
    assert "Configuration error: Error parsing configuration file" in caplog.text

def test_main_real_sync(tmp_path, monkeypatch, capsys):
    source_dir = tmp_path / "src"
    source_dir.mkdir()
    (source_dir / "photo.jpg").write_text("image data content")
    dest_dir = tmp_path / "dest"
    dest_dir.mkdir()
    
    monkeypatch.setattr("sys.argv", [
        "copy-that", 
        "sync",        "--source", str(source_dir), 
        "--dest", str(dest_dir),
        "--mode", "mirror",
        "--no-space-check"
    ])
    
    with pytest.raises(SystemExit) as e:
        main()
    assert e.value.code == 0
    
    expected_file = dest_dir / "photo.jpg"
    assert expected_file.exists()
    assert expected_file.read_text() == "image data content"
    
    captured = capsys.readouterr()
    err_norm = " ".join(captured.err.split())
    assert "Sync Summary" in err_norm
    assert "Total Files Processed: 1" in err_norm
    assert "Copied: 1" in err_norm

def test_main_space_check_triggered(tmp_path, monkeypatch, capsys):
    source_dir = tmp_path / "src"
    source_dir.mkdir()
    (source_dir / "test.jpg").write_text("data")
    dest_dir = tmp_path / "dest"
    dest_dir.mkdir()
    
    monkeypatch.setattr(shutil, "disk_usage", lambda p: shutil._ntuple_diskusage(100, 99, 1))
    
    monkeypatch.setattr("sys.argv", [
        "copy-that",
        "sync",
        "--source", str(source_dir),
        "--dest", str(dest_dir),
        "--space-check",
        "--dry-run"
    ])
    
    with pytest.raises(SystemExit) as e:
        main()
    assert e.value.code == 0
    
    captured = capsys.readouterr()
    err_norm = " ".join(captured.err.split())
    assert "Performing pre-sync disk space check" in err_norm
    assert "Possible insufficient disk" in err_norm

def test_main_filename_date_dry_run(tmp_path, monkeypatch, capsys):
    source_dir = tmp_path / "src"
    source_dir.mkdir()
    filename = "2023-01-01 12.00.00.jpg"
    (source_dir / filename).write_text("data")
    dest_dir = tmp_path / "dest"
    dest_dir.mkdir()
    
    monkeypatch.setattr("sys.argv", [
        "copy-that",
        "sync",
        "--source", str(source_dir),
        "--dest", str(dest_dir),
        "--date-source", "filename",
        "--dry-run"
    ])
    
    with pytest.raises(SystemExit) as e:
        main()
    assert e.value.code == 0
    
    captured = capsys.readouterr()
    err_flat = captured.err.replace("\n", " ")
    assert "Copied" in err_flat
    assert filename in err_flat

def test_main_filename_date_space_check(tmp_path, monkeypatch, capsys):
    source_dir = tmp_path / "src"
    source_dir.mkdir()
    filename = "2023-01-01 12.00.00.jpg"
    (source_dir / filename).write_text("data")
    dest_dir = tmp_path / "dest"
    dest_dir.mkdir()
    
    monkeypatch.setattr(shutil, "disk_usage", lambda p: shutil._ntuple_diskusage(100, 100, 0))
    
    monkeypatch.setattr("sys.argv", [
        "copy-that",
        "sync",
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
    err_norm = " ".join(captured.err.split())
    assert "Performing pre-sync disk space check" in err_norm
    assert "Possible insufficient disk" in err_norm

def test_cli_filename_date_source(tmp_path, monkeypatch, capsys):
    source_dir = tmp_path / "src"
    source_dir.mkdir()
    filename = "2015-12-26 15.13.52-1.jpg"
    (source_dir / filename).write_text("data")
    dest_dir = tmp_path / "dest"
    dest_dir.mkdir()
    
    monkeypatch.setattr("sys.argv", [
        "copy-that", 
        "sync",        "--source", str(source_dir), 
        "--dest", str(dest_dir),
        "--date-source", "filename",
        "--filename-date-format", "%Y-%m-%d %H.%M.%S",
        "--format", "%Y-%m-%d",
        "--no-space-check"
    ])
    
    with pytest.raises(SystemExit) as e:
        main()
    assert e.value.code == 0
    
    expected_file = dest_dir / "2015-12-26" / filename
    assert expected_file.exists()
    assert expected_file.read_text() == "data"
    
    captured = capsys.readouterr()
    assert "Sync Summary" in captured.err

def test_integrity_aware_skip_dry_run(tmp_path, monkeypatch, capsys):
    today = datetime.datetime.now().strftime("%Y%m%d")
    source_dir = tmp_path / "src"
    source_dir.mkdir()
    (source_dir / "test.jpg").write_text("source data")
    dest_dir = tmp_path / "dest"
    dest_dir.mkdir()
    (dest_dir / today).mkdir()
    (dest_dir / today / "test.jpg").write_text("source data")
    
    monkeypatch.setattr("sys.argv", [
        "copy-that",
        "sync",
        "--source", str(source_dir),
        "--dest", str(dest_dir),
        "--verify", "size",
        "--dry-run"
    ])
    
    with pytest.raises(SystemExit) as e:
        main()
    assert e.value.code == 0
    
    captured = capsys.readouterr()
    assert "Skipped" in captured.err

    (dest_dir / today / "test.jpg").write_text("different")
    
    with pytest.raises(SystemExit) as e:
        main()
    assert e.value.code == 0
    
    captured = capsys.readouterr()
    assert "Overwritten" in captured.err

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
        "sync",
        "--source", str(source_dir),
        "--dest", str(dest_dir),
        "--conflict", "rename",
        "--dry-run"
    ])
    
    with pytest.raises(SystemExit) as e:
        main()
    assert e.value.code == 0
    
    captured = capsys.readouterr()
    assert "Renamed" in captured.err
    assert "test_1.jpg" in captured.err

def test_smart_sync_concurrency(tmp_path, monkeypatch, capsys):
    today = datetime.datetime.now().strftime("%Y%m%d")
    source_dir = tmp_path / "src"
    source_dir.mkdir()
    dest_dir = tmp_path / "dest"
    dest_dir.mkdir()
    
    num_files = 20
    for i in range(num_files):
        content = f"content {i}"
        source_file = source_dir / f"file_{i}.txt"
        source_file.write_text(content)
        
        if i % 2 == 0: 
            dest_subdir = dest_dir / today
            dest_subdir.mkdir(exist_ok=True)
            dest_file = dest_subdir / f"file_{i}.txt"
            dest_file.write_text(content)
        else: 
            dest_subdir = dest_dir / today
            dest_subdir.mkdir(exist_ok=True)
            dest_file = dest_subdir / f"file_{i}.txt"
            dest_file.write_text("corrupt")
            
    monkeypatch.setattr("sys.argv", [
        "copy-that",
        "sync",
        "--source", str(source_dir),
        "--dest", str(dest_dir),
        "--verify", "size",
        "--workers", "4",
        "--ext", ".txt" 
    ])
    
    with pytest.raises(SystemExit) as e:
        main()
    assert e.value.code == 0
    
    captured = capsys.readouterr()
    err_norm = " ".join(captured.err.split())
    assert "Total Files Processed: 20" in err_norm
    assert "Copied: 10" in err_norm
    assert "Skipped: 10" in err_norm

def test_main_log_default_path(tmp_path, monkeypatch, capsys):
    source_dir = tmp_path / "src"
    source_dir.mkdir()
    dest_dir = tmp_path / "dest"
    dest_dir.mkdir()
    
    mock_log = tmp_path / "default.log"
    monkeypatch.setattr("copy_that.main.get_default_log_file", lambda: mock_log)
    
    monkeypatch.setattr("sys.argv", [
        "copy-that",
        "sync",
        "--source", str(source_dir),
        "--dest", str(dest_dir),
        "--log",
        "--dry-run",
        "--verbose"
    ])
    with pytest.raises(SystemExit):
        main()
    
    assert mock_log.exists()

def test_main_log_dir_not_writable_capsys(tmp_path, monkeypatch, capsys):
    source_dir = tmp_path / "src"
    source_dir.mkdir()
    dest_dir = tmp_path / "dest"
    dest_dir.mkdir()
    log_file = tmp_path / "no_access" / "test.log"
    
    monkeypatch.setattr("sys.argv", [
        "copy-that",
        "sync",
        "--source", str(source_dir),
        "--dest", str(dest_dir),
        "--log-file", str(log_file),
        "--dry-run",
        "-v"
    ])
    # Use a side effect to only fail for the log directory
    original_access = os.access
    def mocked_access(path, mode):
        if str(path).startswith(str(log_file.parent)):
            return False
        return original_access(path, mode)

    with patch("os.access", side_effect=mocked_access):
        with pytest.raises(SystemExit):
            main()
            
    captured = capsys.readouterr()
    # Since we use AtomicGridHandler, the output is in stderr/stdout via rich
    # We check for a subset of the error message to avoid being sensitive to grid truncation
    assert "Could not initialize log" in captured.err or "Could not initialize log" in captured.out

def test_dry_run_skip_none_verify(tmp_path, monkeypatch, capsys):
    source_dir = tmp_path / "src"
    source_dir.mkdir()
    (source_dir / "test.jpg").write_text("data")
    dest_dir = tmp_path / "dest"
    dest_dir.mkdir()
    (dest_dir / "test.jpg").write_text("exists")
    
    monkeypatch.setattr("sys.argv", [
        "copy-that",
        "sync",
        "--source", str(source_dir),
        "--dest", str(dest_dir),
        "--mode", "mirror",
        "--conflict", "skip",
        "--verify", "none",
        "--dry-run"
    ])
    
    with pytest.raises(SystemExit):
        main()
        
    captured = capsys.readouterr()
    assert "Skipped" in captured.err

def test_dry_run_overwrite_policy(tmp_path, monkeypatch, capsys):
    source_dir = tmp_path / "src"
    source_dir.mkdir()
    (source_dir / "test.jpg").write_text("data")
    dest_dir = tmp_path / "dest"
    dest_dir.mkdir()
    (dest_dir / "test.jpg").write_text("exists")
    
    monkeypatch.setattr("sys.argv", [
        "copy-that",
        "sync",
        "--source", str(source_dir),
        "--dest", str(dest_dir),
        "--mode", "mirror",
        "--conflict", "overwrite",
        "--dry-run"
    ])
    
    with pytest.raises(SystemExit):
        main()
        
    captured = capsys.readouterr()
    assert "Overwritten" in captured.err

def test_main_process_single_file_failed_branch(tmp_path, monkeypatch, capsys):
    source_dir = tmp_path / "src"
    source_dir.mkdir()
    (source_dir / "test.jpg").write_text("data")
    dest_dir = tmp_path / "dest"
    dest_dir.mkdir()
    
    from copy_that.processor import FileResult, SyncStatus
    mock_result = FileResult(SyncStatus.FAILED, source_dir / "test.jpg", dest_dir / "test.jpg", error_message="Simulated failure")
    monkeypatch.setattr("copy_that.main.copy_file", lambda *args, **kwargs: mock_result)
    
    monkeypatch.setattr("sys.argv", [
        "copy-that",
        "sync",
        "--source", str(source_dir),
        "--dest", str(dest_dir),
        "--no-space-check"
    ])
    
    with pytest.raises(SystemExit):
        main()
    
    captured = capsys.readouterr()
    assert "Simulated failure" in captured.err

def test_dry_run_skip_date_mode(tmp_path, monkeypatch, capsys):
    today = datetime.datetime.now().strftime("%Y%m%d")
    source_dir = tmp_path / "src"
    source_dir.mkdir()
    (source_dir / "test.jpg").write_text("data")
    dest_dir = tmp_path / "dest"
    dest_dir.mkdir()
    # Setup for date mode: file must be in the date folder
    (dest_dir / today).mkdir()
    (dest_dir / today / "test.jpg").write_text("data")
    
    monkeypatch.setattr("sys.argv", [
        "copy-that",
        "sync",
        "--source", str(source_dir),
        "--dest", str(dest_dir),
        "--mode", "date",
        "--conflict", "skip",
        "--dry-run"
    ])
    
    with pytest.raises(SystemExit):
        main()
        
    captured = capsys.readouterr()
    assert "Skipped" in captured.err

def test_real_sync_mirror_nested(tmp_path, monkeypatch, capsys):
    source_dir = tmp_path / "src"
    source_dir.mkdir()
    nested = source_dir / "a" / "b"
    nested.mkdir(parents=True)
    (nested / "file.txt").write_text("content")
    
    dest_dir = tmp_path / "dest"
    dest_dir.mkdir()
    
    monkeypatch.setattr("sys.argv", [
        "copy-that",
        "sync",
        "--source", str(source_dir),
        "--dest", str(dest_dir),
        "--mode", "mirror",
        "--ext", ".txt",
        "--no-space-check"
    ])
    
    with pytest.raises(SystemExit):
        main()
        
    expected_file = dest_dir / "a" / "b" / "file.txt"
    assert expected_file.exists()
    assert expected_file.read_text() == "content"
    
    captured = capsys.readouterr()
    err_norm = " ".join(captured.err.split())
    assert "Copied: 1" in err_norm

def test_cli_reliability_flags(tmp_path, monkeypatch, capsys):
    source_dir = tmp_path / "src"
    source_dir.mkdir()
    (source_dir / "test.jpg").write_text("data")
    dest_dir = tmp_path / "dest"
    dest_dir.mkdir()
    
    # We want to capture the config object passed to process_single_file
    captured_configs = []
    
    def mock_process(job, config):
        captured_configs.append(config)
        from copy_that.processor import FileResult, SyncStatus
        return FileResult(SyncStatus.COPIED, job.source, job.destination)
        
    monkeypatch.setattr("copy_that.main.process_single_file", mock_process)
    
    monkeypatch.setattr("sys.argv", [
        "copy-that",
        "sync",
        "--source", str(source_dir),
        "--dest", str(dest_dir),
        "--retries", "5",
        "--retry-delay", "2.5",
        "--no-backoff",
        "--no-space-check"
    ])
    
    with pytest.raises(SystemExit):
        main()
        
    assert len(captured_configs) > 0
    config = captured_configs[0]
    assert config.max_retries == 5
    assert config.retry_base_delay == 2.5
    assert config.retry_exponential_backoff is False
