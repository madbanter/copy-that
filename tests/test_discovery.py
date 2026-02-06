import pytest
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
