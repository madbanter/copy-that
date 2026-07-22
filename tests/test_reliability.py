import pytest
import errno
import os
import time
from pathlib import Path
from unittest.mock import patch, MagicMock
from copy_that.processor import copy_file, SyncStatus


def test_atomic_write_failure_leaves_no_dest(tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("source data")
    dest = tmp_path / "dest.txt"

    # Simulate an error during copy
    def mocked_copyfileobj(fsrc, fdst, length):
        fdst.write(b"partial data")
        raise OSError(errno.EIO, "I/O error during copy")

    with patch("shutil.copyfileobj", side_effect=mocked_copyfileobj):
        # max_retries=0 to fail immediately after one attempt
        result = copy_file(source, dest, max_retries=0)

    assert result.status == SyncStatus.FAILED
    assert not dest.exists()
    # Ensure temp file is also gone
    temp_file = dest.with_suffix(dest.suffix + ".ct-tmp")
    assert not temp_file.exists()


def test_atomic_write_preserves_existing_on_failure(tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("new data")
    dest = tmp_path / "dest.txt"
    dest.write_text("old data")

    # Simulate an error during copy
    with patch("shutil.copyfileobj", side_effect=OSError(errno.EIO, "I/O error")):
        result = copy_file(source, dest, conflict_policy="overwrite", max_retries=0)

    assert result.status == SyncStatus.FAILED
    assert dest.exists()
    assert dest.read_text() == "old data"


def test_retry_on_transient_error_success(tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("retry success data")
    dest = tmp_path / "dest.txt"

    # Simulate: 1st attempt fails with EIO, 2nd succeeds
    call_count = 0
    original_copyfileobj = __import__("shutil").copyfileobj

    def mocked_copyfileobj(fsrc, fdst, length):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise OSError(errno.EIO, "Transient I/O error")
        return original_copyfileobj(fsrc, fdst, length)

    with patch("shutil.copyfileobj", side_effect=mocked_copyfileobj):
        with patch("time.sleep") as mock_sleep:
            result = copy_file(source, dest, max_retries=3, retry_base_delay=1.0)

    assert result.status == SyncStatus.COPIED
    assert result.retried is True
    assert call_count == 2
    assert dest.read_text() == "retry success data"
    assert mock_sleep.call_count == 1
    mock_sleep.assert_called_with(1.0)


def test_retry_exhaustion_failure(tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("always fails")
    dest = tmp_path / "dest.txt"

    # Always fail with EIO
    with patch(
        "shutil.copyfileobj", side_effect=OSError(errno.EIO, "Persistent I/O error")
    ):
        with patch("time.sleep") as mock_sleep:
            result = copy_file(source, dest, max_retries=2, retry_base_delay=1.0)

    assert result.status == SyncStatus.FAILED
    assert result.error_message and "Retries exhausted" in result.error_message
    assert (
        mock_sleep.call_count == 2
    )  # Attempt 1 (fail, sleep), Attempt 2 (fail, sleep), Attempt 3 (fail, done)
    # 1.0s then 2.0s (exponential backoff)
    mock_sleep.assert_any_call(1.0)
    mock_sleep.assert_any_call(2.0)


def test_no_retry_on_terminal_error(tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("terminal error")
    dest = tmp_path / "dest.txt"

    # ENOSPC (Disk Full) is terminal
    with patch(
        "shutil.copyfileobj", side_effect=OSError(errno.ENOSPC, "No space left")
    ):
        with patch("time.sleep") as mock_sleep:
            result = copy_file(source, dest, max_retries=3)

    assert result.status == SyncStatus.FAILED
    assert result.error_message and "No space left" in result.error_message
    assert result.retried is False
    assert mock_sleep.call_count == 0


def test_atomic_write_success_renames(tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("success data")
    dest = tmp_path / "dest.txt"

    # We want to verify that os.replace is called
    with patch("os.replace", wraps=os.replace) as mock_replace:
        result = copy_file(source, dest)

    assert result.status == SyncStatus.COPIED
    assert dest.exists()
    assert dest.read_text() == "success data"
    assert mock_replace.called


def test_copy_file_source_missing_graceful(tmp_path):
    source = tmp_path / "nonexistent.txt"
    dest = tmp_path / "dest.txt"

    # Should not crash, but return a failed FileResult
    result = copy_file(source, dest)

    assert result.status == SyncStatus.FAILED
    assert result.error_message and "Source file inaccessible" in result.error_message
    assert not dest.exists()


def test_graceful_cleanup_of_temp_files(tmp_path):
    from copy_that.config import Config
    from copy_that.main import run_sync
    import copy_that.main
    
    source_dir = tmp_path / "src"
    source_dir.mkdir()
    (source_dir / "file1.jpg").write_text("data")
    dest_dir = tmp_path / "dest"
    dest_dir.mkdir()
    
    config = Config(
        source_directory=source_dir,
        destination_base=dest_dir,
        max_workers=1,
        pre_sync_space_check=False
    )
    
    # Create a dummy temp file that we want to simulate is currently being written
    dummy_temp = dest_dir / "dummy.jpg.ct-tmp"
    dummy_temp.write_text("partial data")
    
    # Mock run_sync_jobs to insert our dummy_temp into _active_temp_files and raise ValueError
    def mock_run_sync_jobs(sync_jobs, config, stats):
        copy_that.main._active_temp_files.add(dummy_temp)
        raise ValueError("Simulated crash")
        
    with patch("copy_that.main.run_sync_jobs", side_effect=mock_run_sync_jobs):
        with pytest.raises(ValueError, match="Simulated crash"):
            run_sync(config, show_summary=False)
            
    # Verify that the dummy temp file was cleaned up by the finally block of run_sync
    assert not dummy_temp.exists()


