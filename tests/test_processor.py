import pytest
import hashlib
import shutil
import time
from pathlib import Path
from unittest.mock import patch, MagicMock
from copy_that.processor import copy_file, calculate_checksum, verify_copy, get_unique_path, SyncStatus, FileResult

def test_calculate_checksum(tmp_path):
    file_path = tmp_path / "test.txt"
    file_path.write_text("hello world")
    
    # MD5 of "hello world" is 5eb63bbbe01eeed093cb22bb8f5acdc3
    assert calculate_checksum(file_path, "md5") == "5eb63bbbe01eeed093cb22bb8f5acdc3"
    
    # SHA1 of "hello world" is 2aae6c35c94fcfb415dbe95f408b9ce91ee846ed
    assert calculate_checksum(file_path, "sha1") == "2aae6c35c94fcfb415dbe95f408b9ce91ee846ed"

def test_calculate_checksum_file_digest(tmp_path, monkeypatch):
    file_path = tmp_path / "test.txt"
    file_path.write_text("hello world")
    
    # Mock hashlib.file_digest to return a known value
    class MockHash:
        def hexdigest(self):
            return "mocked_hash"
            
    mock_digest_called = False
    def mocked_file_digest(f, algo):
        nonlocal mock_digest_called
        mock_digest_called = True
        return MockHash()
        
    # Force the mock even if it exists
    monkeypatch.setattr(hashlib, "file_digest", mocked_file_digest, raising=False)
    
    result = calculate_checksum(file_path, "md5")
    assert result == "mocked_hash"
    assert mock_digest_called is True

def test_verify_copy_size(tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("hello")
    dest = tmp_path / "dest.txt"
    dest.write_text("hello")
    
    assert verify_copy(source, dest, "size") is True
    
    dest.write_text("world!")
    assert verify_copy(source, dest, "size") is False

def test_verify_copy_md5(tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("hello")
    dest = tmp_path / "dest.txt"
    dest.write_text("hello")
    
    assert verify_copy(source, dest, "md5") is True
    
    dest.write_text("hallo")
    assert verify_copy(source, dest, "md5") is False

def test_verify_copy_unknown_method(caplog):
    # Should not crash, return False (fail-closed)
    with caplog.at_level("ERROR"):
        assert verify_copy(Path("any"), Path("any"), "unknown") is False
    assert "Unknown verification method: unknown" in caplog.text

def test_verify_copy_os_error(caplog):
    # Trigger OSError in verify_copy (e.g. file doesn't exist when stat'ing)
    with caplog.at_level("ERROR"):
        result = verify_copy(Path("nonexistent_source"), Path("nonexistent_dest"), method="size")
    assert result is False
    assert "Could not verify" in caplog.text

def test_copy_file_with_verification(tmp_path):
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    dest_dir = tmp_path / "dest"
    dest_dir.mkdir()
    
    source_file = source_dir / "test.jpg"
    content = "fake image data"
    source_file.write_text(content)
    
    dest_file = dest_dir / "test.jpg"
    
    # Test successful copy with MD5 verification
    result = copy_file(source_file, dest_file, verification_method="md5")
    assert result.status == SyncStatus.COPIED
    assert result.bytes_transferred == len(content)
    assert dest_file.exists()
    assert dest_file.read_text() == content

def test_copy_file_verification_failure_delete(tmp_path, monkeypatch):
    source_file = tmp_path / "source.txt"
    source_file.write_text("important data")
    dest_file = tmp_path / "dest.txt"
    
    # Mock verify_copy to simulate a failure
    import copy_that.processor
    monkeypatch.setattr(copy_that.processor, "verify_copy", lambda s, d, m, buffer_size=1048576: False)
    
    result = copy_file(source_file, dest_file, verification_method="md5", verification_failure_behavior="delete")
    assert result.status == SyncStatus.FAILED
    assert result.error_message == "Verification failed and file deleted"
    assert not dest_file.exists()
    assert source_file.exists() # Ensure source is NEVER deleted

def test_copy_file_verification_failure_ignore(tmp_path, monkeypatch):
    source_file = tmp_path / "source.txt"
    content = "important data"
    source_file.write_text(content)
    dest_file = tmp_path / "dest.txt"
    
    # Mock verify_copy to simulate a failure
    import copy_that.processor
    monkeypatch.setattr(copy_that.processor, "verify_copy", lambda s, d, m, buffer_size=1048576: False)
    
    result = copy_file(source_file, dest_file, verification_method="md5", verification_failure_behavior="ignore")
    assert result.status == SyncStatus.COPIED
    assert result.bytes_transferred == len(content)
    assert dest_file.exists()

def test_copy_file_verification_failure_retry(tmp_path, monkeypatch, caplog):
    source_file = tmp_path / "source.txt"
    content = "retry data"
    source_file.write_text(content)
    dest_file = tmp_path / "dest.txt"
    
    # Simulate: first call fails verification, second call (retry) succeeds.
    verify_results = [False, True]
    def mock_verify(*args, **kwargs):
        return verify_results.pop(0) if verify_results else True
        
    import copy_that.processor
    monkeypatch.setattr(copy_that.processor, "verify_copy", mock_verify)
    
    # Disable delay for faster tests
    with caplog.at_level("WARNING"):
        result = copy_file(source_file, dest_file, verification_method="md5", verification_failure_behavior="retry", retry_base_delay=0)

    # In new implementation, it stays COPIED if it didn't exist at start
    assert result.status == SyncStatus.COPIED
    assert result.retried is True
    assert "Retry attempt 1" in caplog.text

    assert dest_file.exists()

def test_copy_file_unsupported_failure_behavior(tmp_path, monkeypatch):
    source = tmp_path / "source.txt"
    source.write_text("data")
    dest = tmp_path / "dest.txt"
    dest.write_text("corrupt")
    
    # Force verification failure
    monkeypatch.setattr("copy_that.processor.verify_copy", lambda *args, **kwargs: False)
    
    # Passing an unsupported behavior should hit the 'else' branch
    result = copy_file(source, dest, verification_method="size", verification_failure_behavior="invalid")
    assert result.status == SyncStatus.FAILED
    assert result.error_message == "Verification failed"

def test_conflict_policy_skip(tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("source content")
    dest = tmp_path / "dest.txt"
    dest.write_text("existing content")
    
    result = copy_file(source, dest, conflict_policy="skip")
    assert result.status == SyncStatus.SKIPPED
    assert result.bytes_transferred == 0
    assert dest.read_text() == "existing content"

def test_conflict_policy_overwrite(tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("source content")
    dest = tmp_path / "dest.txt"
    dest.write_text("existing content")
    
    result = copy_file(source, dest, conflict_policy="overwrite")
    assert result.status == SyncStatus.OVERWRITTEN
    assert result.bytes_transferred == len("source content")
    assert dest.read_text() == "source content"

def test_conflict_policy_rename(tmp_path):
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    dst_dir = tmp_path / "dst"
    dst_dir.mkdir()
    
    source = src_dir / "image.jpg"
    source.write_text("new data")
    
    dest = dst_dir / "image.jpg"
    dest.write_text("old data")
    
    result = copy_file(source, dest, conflict_policy="rename")
    assert result.status == SyncStatus.RENAMED
    assert result.bytes_transferred == len("new data")
    assert dest.exists()
    assert dest.read_text() == "old data"
    renamed_dest = dst_dir / "image_1.jpg"
    assert renamed_dest.exists()
    assert renamed_dest.read_text() == "new data"

def test_get_unique_path(tmp_path):
    base_path = tmp_path / "test.txt"
    assert get_unique_path(base_path) == base_path
    
    base_path.write_text("exist")
    path_1 = get_unique_path(base_path)
    assert path_1 == tmp_path / "test_1.txt"
    
    path_1.write_text("1")
    path_2 = get_unique_path(base_path)
    assert path_2 == tmp_path / "test_2.txt"

def test_copy_file_skip_with_verification_success(tmp_path, caplog):
    source = tmp_path / "source.txt"
    dest = tmp_path / "dest.txt"
    content = "identical content"
    source.write_text(content)
    dest.write_text(content)
    
    with caplog.at_level("DEBUG"):
        result = copy_file(source, dest, conflict_policy="skip", verification_method="size")
    assert result.status == SyncStatus.SKIPPED

def test_copy_file_skip_with_verification_failure(tmp_path, caplog):
    source = tmp_path / "source.txt"
    dest = tmp_path / "dest.txt"
    source_content = "source content"
    source.write_text(source_content)
    dest.write_text("different")
    
    with caplog.at_level("WARNING"):
        result = copy_file(source, dest, conflict_policy="skip", verification_method="size")
    assert result.status == SyncStatus.OVERWRITTEN
    assert dest.read_text() == source_content

def test_copy_file_skip_with_cryptographic_verification(tmp_path):
    source = tmp_path / "source.txt"
    dest = tmp_path / "dest.txt"
    content = "hello world"
    source.write_text(content)
    dest.write_text(content)
    
    result = copy_file(source, dest, conflict_policy="skip", verification_method="md5")
    assert result.status == SyncStatus.SKIPPED
    
    dest.write_text("olleh dlrow")
    result = copy_file(source, dest, conflict_policy="skip", verification_method="md5")
    assert result.status == SyncStatus.OVERWRITTEN
    assert dest.read_text() == content

def test_copy_file_failed_copy(tmp_path):
    source_file = tmp_path / "source.txt"
    source_file.write_text("data")
    dest_file = tmp_path / "dest.txt"
    
    # We use os.replace now, but open() still happens first
    with patch("builtins.open", side_effect=PermissionError("Mocked write error")):
        result = copy_file(source_file, dest_file)
        
    assert result.status == SyncStatus.FAILED
    assert "Mocked write error" in result.error_message

def test_copy_file_permission_error(tmp_path, monkeypatch):
    source = tmp_path / "source.txt"
    source.write_text("data")
    dest = tmp_path / "dest.txt"
    
    def mocked_copyfileobj(fsrc, fdst, length):
        raise PermissionError("Permission denied")
    
    monkeypatch.setattr(shutil, "copyfileobj", mocked_copyfileobj)
    
    result = copy_file(source, dest)
    assert result.status == SyncStatus.FAILED
    assert "Permission denied" in result.error_message


def test_copy_file_copystat_oserror_utime_fallback(tmp_path, monkeypatch, caplog):
    """copystat OSError triggers utime fallback; file is still successfully copied."""
    source = tmp_path / "source.txt"
    source.write_text("data")
    dest = tmp_path / "dest.txt"

    monkeypatch.setattr(shutil, "copystat", MagicMock(side_effect=OSError("copystat not supported")))

    import logging
    with caplog.at_level(logging.DEBUG, logger="copy_that.processor"):
        result = copy_file(source, dest)

    assert result.status == SyncStatus.COPIED
    assert dest.read_text() == "data"
    assert "copystat failed" in caplog.text


def test_copy_file_copystat_and_utime_both_fail(tmp_path, monkeypatch, caplog):
    """When both copystat and os.utime fail, a warning is logged but copy still succeeds."""
    import os as _os
    source = tmp_path / "source.txt"
    source.write_text("data")
    dest = tmp_path / "dest.txt"

    monkeypatch.setattr(shutil, "copystat", MagicMock(side_effect=OSError("copystat failed")))
    monkeypatch.setattr(_os, "utime", MagicMock(side_effect=OSError("utime failed")))

    import logging
    with caplog.at_level(logging.WARNING, logger="copy_that.processor"):
        result = copy_file(source, dest)

    assert result.status == SyncStatus.COPIED
    assert "Could not preserve timestamps" in caplog.text


def test_get_unique_path_with_lock_and_allocated(tmp_path):
    """get_unique_path with lock= correctly allocates via the in-memory set."""
    import threading
    lock = threading.Lock()
    allocated: set = set()

    base = tmp_path / "image.jpg"
    # Path does not exist on disk; first call returns base and registers it
    result1 = get_unique_path(base, allocated_paths=allocated, lock=lock)
    assert result1 == base
    assert base in allocated

    # Second call: base is now allocated, should return image_1.jpg
    result2 = get_unique_path(base, allocated_paths=allocated, lock=lock)
    assert result2 == tmp_path / "image_1.jpg"
    assert result2 in allocated


def test_get_unique_path_allocated_only_no_disk(tmp_path):
    """get_unique_path without a lock still respects the allocated_paths set."""
    allocated: set = set()
    base = tmp_path / "photo.jpg"

    r1 = get_unique_path(base, allocated_paths=allocated, lock=None)
    assert r1 == base
    assert base in allocated

    r2 = get_unique_path(base, allocated_paths=allocated, lock=None)
    assert r2 == tmp_path / "photo_1.jpg"


def test_is_retryable_error_non_oserror():
    """is_retryable_error returns False for non-OSError exceptions."""
    from copy_that.processor import is_retryable_error
    assert is_retryable_error(ValueError("not an OS error")) is False
    assert is_retryable_error(RuntimeError("also not")) is False


def test_conflict_skip_allocated_not_on_disk(tmp_path):
    """copy_file skips when destination is allocated in-memory but not yet on disk."""
    import threading
    source = tmp_path / "source.txt"
    source.write_text("data")
    dest = tmp_path / "dest.txt"  # intentionally not created on disk

    allocated: set = {dest}  # pre-register as allocated
    lock = threading.Lock()

    result = copy_file(
        source, dest,
        conflict_policy="skip",
        allocated_paths=allocated,
        allocated_lock=lock,
    )
    assert result.status == SyncStatus.SKIPPED
    assert not dest.exists()


def test_copy_file_active_temp_files_lockless(tmp_path):
    """active_temp_files add/discard path when active_temp_lock is None (lockless variant)."""
    source = tmp_path / "source.txt"
    source.write_text("hello")
    dest = tmp_path / "dest.txt"

    active: set = set()

    result = copy_file(
        source, dest,
        active_temp_files=active,
        active_temp_lock=None,  # exercise the lockless branch
    )

    assert result.status == SyncStatus.COPIED
    assert dest.read_text() == "hello"
    # Temp file should have been discarded from the set after successful rename
    temp = dest.with_suffix(dest.suffix + ".ct-tmp")
    assert temp not in active


def test_copy_file_concurrent_same_destination_rename(tmp_path):
    """Verify concurrent workers targeting the same new destination resolve unique paths without racing."""
    import concurrent.futures
    import threading

    source1 = tmp_path / "source1.txt"
    source2 = tmp_path / "source2.txt"
    source1.write_text("content 1")
    source2.write_text("content 2")

    target = tmp_path / "output.txt"
    allocated_paths = set()
    lock = threading.Lock()

    def run_worker(src):
        return copy_file(
            src,
            target,
            conflict_policy="rename",
            allocated_paths=allocated_paths,
            allocated_lock=lock,
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(run_worker, source1), executor.submit(run_worker, source2)]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]

    assert len(results) == 2
    statuses = {r.status for r in results}
    destinations = {r.destination_path for r in results}

    assert SyncStatus.COPIED in statuses
    assert SyncStatus.RENAMED in statuses
    assert len(destinations) == 2
    assert target in destinations
    assert (tmp_path / "output_1.txt") in destinations
    assert {
        target.read_text(),
        (tmp_path / "output_1.txt").read_text(),
    } == {"content 1", "content 2"}


def test_copy_file_failed_verification_rename_recalculation(tmp_path):
    """Verify that a failed verification under skip policy recalculates/reserves destination under lock when re-copying."""
    import threading

    source = tmp_path / "source.txt"
    source.write_text("new content")
    dest = tmp_path / "output.txt"
    dest.write_text("old corrupt content")

    allocated_paths = set()
    lock = threading.Lock()

    # Call 1: skip check verify_copy fails -> logger.warning, status=OVERWRITTEN
    # Call 2: copy verification succeeds -> return FileResult
    call_count = 0
    def mock_verify(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return False if call_count == 1 else True

    with patch("copy_that.processor.verify_copy", side_effect=mock_verify):
        result = copy_file(
            source=source,
            destination=dest,
            conflict_policy="skip",
            verification_method="size",
            allocated_paths=allocated_paths,
            allocated_lock=lock,
        )

    assert result.status == SyncStatus.OVERWRITTEN
    assert result.destination_path == dest
    assert dest.read_text() == "new content"
    assert dest in allocated_paths


