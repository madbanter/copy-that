import pytest
import os
from pathlib import Path
from copy_that.discovery import discover_files

def test_discover_files_case_insensitive(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    
    # Create files with different cases
    (source / "image1.JPG").touch()
    (source / "image2.jpg").touch()
    (source / "image3.Jpeg").touch()
    (source / "doc1.pdf").touch()
    (source / "RAW1.ARW").touch()
    
    extensions = [".jpg", ".jpeg", ".arw"]
    
    found_files = list(discover_files(source, extensions))
    
    filenames = {f.name for f in found_files}
    assert len(found_files) == 4
    assert "image1.JPG" in filenames
    assert "image2.jpg" in filenames
    assert "image3.Jpeg" in filenames
    assert "RAW1.ARW" in filenames
    assert "doc1.pdf" not in filenames

def test_discover_files_recursive(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    
    sub1 = source / "sub1"
    sub1.mkdir()
    sub2 = sub1 / "sub2"
    sub2.mkdir()
    
    (source / "file1.jpg").touch()
    (sub1 / "file2.jpg").touch()
    (sub2 / "file3.jpg").touch()
    (sub2 / "ignore.txt").touch()
    
    extensions = [".jpg"]
    
    found_files = list(discover_files(source, extensions))
    
    filenames = {f.name for f in found_files}
    assert len(found_files) == 3
    assert "file1.jpg" in filenames
    assert "file2.jpg" in filenames
    assert "file3.jpg" in filenames
    assert "ignore.txt" not in filenames

def test_discover_files_permission_error(tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    
    def mocked_scandir(path):
        raise PermissionError("Access denied")
    
    monkeypatch.setattr(os, "scandir", mocked_scandir)
    
    # Should not crash, just yield nothing and log a warning
    found_files = list(discover_files(source, [".jpg"]))
    assert len(found_files) == 0

def test_discover_files_entry_error(tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    (source / "test.jpg").touch()
    
    # Mocking entry.is_file to raise an error
    original_scandir = os.scandir
    
    class MockEntry:
        def __init__(self, path):
            self.path = path
            self.name = os.path.basename(path)
        def is_file(self):
            raise PermissionError("Entry error")
        def is_dir(self, follow_symlinks=False):
            return False

    class MockScandir:
        def __init__(self, path):
            self.path = path
        def __enter__(self):
            return [MockEntry(os.path.join(self.path, "test.jpg"))]
        def __exit__(self, *args):
            pass

    monkeypatch.setattr(os, "scandir", MockScandir)
    
    # Should skip the problematic entry and continue
    found_files = list(discover_files(source, [".jpg"]))
    assert len(found_files) == 0
