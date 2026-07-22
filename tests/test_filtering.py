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

def test_discover_files_exclude_relative_glob(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    
    keep_dir = source / "keep"
    keep_dir.mkdir()
    (keep_dir / "file1.jpg").write_text("file1")
    
    skip_dir = source / "skip_me"
    skip_dir.mkdir()
    (skip_dir / "file2.jpg").write_text("file2")
    
    # Exclude via relative glob path pattern
    results = list(discover_files(source, [".jpg"], exclude_patterns=["skip_me/*"]))
    
    assert len(results) == 1
    assert results[0][0].name == "file1.jpg"


def test_file_filter_path_outside_source_dir(tmp_path):
    """FileFilter.should_exclude falls back to bare name when path is outside source_dir."""
    from copy_that.discovery import FileFilter

    source = tmp_path / "source"
    source.mkdir()
    outside = tmp_path / "other" / "image.jpg"
    outside.parent.mkdir()
    outside.write_text("data")

    # Pattern matches the bare filename; relative_to will raise ValueError (outside source)
    ff = FileFilter(source, exclude_patterns=["image.jpg"])
    assert ff.should_exclude(outside) is True

    # Pattern that would only match a relative path should NOT match, but name match takes precedence
    ff2 = FileFilter(source, exclude_patterns=["other/image.jpg"])
    # "other/image.jpg" won't match name "image.jpg" nor the fallback (which is also just "image.jpg")
    assert ff2.should_exclude(outside) is False
