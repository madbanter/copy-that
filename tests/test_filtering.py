import pytest
from pathlib import Path
from copy_that.discovery import discover_files

def test_discover_files_glob_exclude(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "keep.jpg").write_text("keep")
    (source / "exclude_me.jpg").write_text("exclude")
    (source / "temp_file.tmp").write_text("temp")
    
    # We want to keep keep.jpg, but exclude anything starting with exclude_ or ending in .tmp
    # Note: extensions already filters out .tmp, so we test exclude_me.jpg
    results = list(discover_files(source, [".jpg"], exclude_patterns=["exclude_*"]))
    
    assert len(results) == 1
    assert results[0][0].name == "keep.jpg"

def test_discover_files_regex_exclude(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "keep.jpg").write_text("keep")
    (source / "ignore_123.jpg").write_text("ignore")
    
    # Exclude files with 'ignore' followed by digits in their name
    results = list(discover_files(source, [".jpg"], exclude_regex=[r"ignore_\d+"]))
    
    assert len(results) == 1
    assert results[0][0].name == "keep.jpg"

def test_discover_files_exclude_directory(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    
    keep_dir = source / "keep"
    keep_dir.mkdir()
    (keep_dir / "file1.jpg").write_text("file1")
    
    skip_dir = source / "skip_me"
    skip_dir.mkdir()
    (skip_dir / "file2.jpg").write_text("file2")
    
    # Exclude the "skip_me" directory via glob
    results = list(discover_files(source, [".jpg"], exclude_patterns=["skip_me"]))
    
    assert len(results) == 1
    assert results[0][0].name == "file1.jpg"

def test_discover_files_exclude_directory_regex(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    
    keep_dir = source / "keep"
    keep_dir.mkdir()
    (keep_dir / "file1.jpg").write_text("file1")
    
    skip_dir = source / "skip_me"
    skip_dir.mkdir()
    (skip_dir / "file2.jpg").write_text("file2")
    
    # Exclude the "skip_me" directory via regex
    results = list(discover_files(source, [".jpg"], exclude_regex=[r"skip_me"]))
    
    assert len(results) == 1
    assert results[0][0].name == "file1.jpg"
