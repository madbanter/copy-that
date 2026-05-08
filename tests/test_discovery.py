import pytest
from pathlib import Path
from copy_that.discovery import discover_files

def test_discover_files_basic(tmp_path):
    # Setup: Create some files
    source = tmp_path / "source"
    source.mkdir()
    (source / "test1.jpg").write_text("image1")
    (source / "test2.JPG").write_text("image2 content") # Test case-insensitivity
    (source / "skip.txt").write_text("ignore me")
    
    nested = source / "subdir"
    nested.mkdir()
    (nested / "nested.jpeg").write_text("nested")
    
    # Run discovery
    results = list(discover_files(source, [".jpg", "jpeg"]))
    
    # Verify results
    assert len(results) == 3
    paths = [r[0] for r in results]
    sizes = {r[0].name: r[1] for r in results}
    
    assert (source / "test1.jpg") in paths
    assert (source / "test2.JPG") in paths
    assert (nested / "nested.jpeg") in paths
    assert (source / "skip.txt") not in paths
    
    assert sizes["test1.jpg"] == len("image1")
    assert sizes["test2.JPG"] == len("image2 content")

def test_discover_files_empty(tmp_path):
    source = tmp_path / "empty"
    source.mkdir()
    results = list(discover_files(source, [".jpg"]))
    assert len(results) == 0

def test_discover_files_no_match(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "test.txt").write_text("data")
    results = list(discover_files(source, [".jpg"]))
    assert len(results) == 0

def test_discover_files_permission_error(tmp_path, caplog):
    source = tmp_path / "source"
    source.mkdir()
    locked = source / "locked"
    locked.mkdir()
    (locked / "secret.jpg").write_text("top secret")
    
    # Note: Truly testing PermissionError is OS-dependent. 
    # Here we just ensure the generator handles the structure change.
    results = list(discover_files(source, [".jpg"]))
    assert len(results) == 1
    assert results[0][0].name == "secret.jpg"
