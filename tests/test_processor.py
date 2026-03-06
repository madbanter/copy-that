import pytest
from pathlib import Path
from copy_that.processor import copy_file, calculate_checksum, verify_copy, get_unique_path

def test_calculate_checksum(tmp_path):
    file_path = tmp_path / "test.txt"
    file_path.write_text("hello world")
    
    # MD5 of "hello world" is 5eb63bbbe01eeed093cb22bb8f5acdc3
    assert calculate_checksum(file_path, "md5") == "5eb63bbbe01eeed093cb22bb8f5acdc3"
    
    # SHA1 of "hello world" is 2aae6c35c94fcfb415dbe95f408b9ce91ee846ed
    assert calculate_checksum(file_path, "sha1") == "2aae6c35c94fcfb415dbe95f408b9ce91ee846ed"

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

def test_copy_file_with_verification(tmp_path):
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    dest_dir = tmp_path / "dest"
    dest_dir.mkdir()
    
    source_file = source_dir / "test.jpg"
    source_file.write_text("fake image data")
    
    dest_file = dest_dir / "test.jpg"
    
    # Test successful copy with MD5 verification
    assert copy_file(source_file, dest_file, verification_method="md5") is True
    assert dest_file.exists()
    assert dest_file.read_text() == "fake image data"

def test_copy_file_verification_failure_delete(tmp_path, monkeypatch):
    source_file = tmp_path / "source.txt"
    source_file.write_text("important data")
    dest_file = tmp_path / "dest.txt"
    
    # Mock verify_copy to simulate a failure
    import copy_that.processor
    monkeypatch.setattr(copy_that.processor, "verify_copy", lambda s, d, m: False)
    
    assert copy_file(source_file, dest_file, verification_method="md5", verification_failure_behavior="delete") is False
    assert not dest_file.exists()
    assert source_file.exists() # Ensure source is NEVER deleted

def test_copy_file_verification_failure_ignore(tmp_path, monkeypatch):
    source_file = tmp_path / "source.txt"
    source_file.write_text("important data")
    dest_file = tmp_path / "dest.txt"
    
    # Mock verify_copy to simulate a failure
    import copy_that.processor
    monkeypatch.setattr(copy_that.processor, "verify_copy", lambda s, d, m: False)
    
    assert copy_file(source_file, dest_file, verification_method="md5", verification_failure_behavior="ignore") is True
    assert dest_file.exists()

def test_copy_file_verification_failure_retry(tmp_path, monkeypatch):
    source_file = tmp_path / "source.txt"
    source_file.write_text("important data")
    dest_file = tmp_path / "dest.txt"
    
    # Track calls to verify_copy
    calls = []
    import copy_that.processor
    original_verify = copy_that.processor.verify_copy
    
    def mocked_verify(s, d, m):
        calls.append(True)
        if len(calls) == 1:
            return False # Fail first time
        return True # Succeed second time
    
    monkeypatch.setattr(copy_that.processor, "verify_copy", mocked_verify)
    
    assert copy_file(source_file, dest_file, verification_method="md5", verification_failure_behavior="retry") is True
    assert len(calls) == 2
    assert dest_file.exists()

def test_conflict_policy_skip(tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("source content")
    dest = tmp_path / "dest.txt"
    dest.write_text("existing content")
    
    assert copy_file(source, dest, conflict_policy="skip") is False
    assert dest.read_text() == "existing content"

def test_conflict_policy_overwrite(tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("source content")
    dest = tmp_path / "dest.txt"
    dest.write_text("existing content")
    
    assert copy_file(source, dest, conflict_policy="overwrite") is True
    assert dest.read_text() == "source content"

def test_conflict_policy_rename(tmp_path):
    # Setup directories
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    dst_dir = tmp_path / "dst"
    dst_dir.mkdir()
    
    source = src_dir / "image.jpg"
    source.write_text("new data")
    
    dest = dst_dir / "image.jpg"
    dest.write_text("old data")
    
    # Perform copy with rename policy
    assert copy_file(source, dest, conflict_policy="rename") is True
    
    # The original dest should still have old data
    assert dest.exists()
    assert dest.read_text() == "old data"
    
    # A new file should be created with new data
    renamed_dest = dst_dir / "image_1.jpg"
    assert renamed_dest.exists()
    assert renamed_dest.read_text() == "new data"

def test_get_unique_path(tmp_path):
    base_path = tmp_path / "test.txt"
    base_path.write_text("0")
    
    path_1 = get_unique_path(base_path)
    assert path_1 == tmp_path / "test_1.txt"
    
    path_1.write_text("1")
    path_2 = get_unique_path(base_path)
    assert path_2 == tmp_path / "test_2.txt"

def test_copy_file_permission_error(tmp_path, monkeypatch):
    source = tmp_path / "source.txt"
    source.write_text("data")
    dest = tmp_path / "dest.txt"
    
    import shutil
    def mocked_copy2(s, d):
        raise PermissionError("Permission denied")
    
    monkeypatch.setattr(shutil, "copy2", mocked_copy2)
    
    # Should log error and return False instead of crashing
    assert copy_file(source, dest) is False
