import pytest
import hashlib
from pathlib import Path
from unittest.mock import patch
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
    assert result.status == SyncStatus.COPIED # Status is still COPIED but it's "at risk"
    assert result.bytes_transferred == len(content)
    assert dest_file.exists()
    
def test_copy_file_verification_failure_retry(tmp_path, monkeypatch, caplog):
    source_file = tmp_path / "source.txt"
    content = "retry data"
    source_file.write_text(content)
    dest_file = tmp_path / "dest.txt"
    
    # We want to simulate: first call fails verification, second call (retry) succeeds.
    # We need to mock verify_copy to return False once, then True.
    verify_results = [False, True]
    def mock_verify(*args, **kwargs):
        return verify_results.pop(0) if verify_results else True
        
    import copy_that.processor
    monkeypatch.setattr(copy_that.processor, "verify_copy", mock_verify)
    
    with caplog.at_level("WARNING"):
        result = copy_file(source_file, dest_file, verification_method="md5", verification_failure_behavior="retry")
    
    assert result.status == SyncStatus.OVERWRITTEN
    assert "Retrying copy" in caplog.text
    assert dest_file.exists()

def test_copy_file_failed_copy(tmp_path, monkeypatch):
    source_file = tmp_path / "source.txt"
    source_file.write_text("data")
    dest_file = tmp_path / "dest.txt"
    
    # We need to mock the builtin open inside copy_file's context or similar.
    with patch("builtins.open", side_effect=PermissionError("Mocked write error")):
        result = copy_file(source_file, dest_file)
        
    assert result.status == SyncStatus.FAILED
    assert "Mocked write error" in result.error_message

def test_integrity_aware_skip_success(tmp_path, monkeypatch, caplog):
    source_file = tmp_path / "source.txt"
    source_file.write_text("same")
    dest_file = tmp_path / "dest.txt"
    dest_file.write_text("same")
    
    # Should skip because verification passes
    with caplog.at_level("WARNING"):
        result = copy_file(source_file, dest_file, verification_method="size")
        
    assert result.status == SyncStatus.SKIPPED
    assert "Skipping (verification successful)" in caplog.text

def test_integrity_aware_skip_failure(tmp_path, monkeypatch, caplog):
    source_file = tmp_path / "source.txt"
    source_file.write_text("new content")
    dest_file = tmp_path / "dest.txt"
    dest_file.write_text("old")
    
    # Should NOT skip because verification fails, should overwrite
    with caplog.at_level("WARNING"):
        result = copy_file(source_file, dest_file, verification_method="size")
        
    assert result.status == SyncStatus.OVERWRITTEN
    assert dest_file.read_text() == "new content"

def test_get_unique_path(tmp_path):
    file_path = tmp_path / "test.txt"
    assert get_unique_path(file_path) == file_path
    
    file_path.write_text("exist")
    unique_1 = tmp_path / "test_1.txt"
    assert get_unique_path(file_path) == unique_1
    
    unique_1.write_text("exist")
    unique_2 = tmp_path / "test_2.txt"
    assert get_unique_path(file_path) == unique_2

def test_copy_file_rename_policy(tmp_path):
    source_file = tmp_path / "test.txt"
    source_file.write_text("data")
    dest_file = tmp_path / "test.txt"
    dest_file.write_text("original")
    
    result = copy_file(source_file, dest_file, conflict_policy="rename")
    assert result.status == SyncStatus.RENAMED
    assert result.destination_path.name == "test_1.txt"
    assert result.destination_path.exists()
    assert dest_file.read_text() == "original"
