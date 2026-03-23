import datetime
import os
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from copy_that.organizer import generate_destination_path, get_file_date

def test_path_structure_date(tmp_path):
    source_root = tmp_path / "src"
    source_root.mkdir()
    source = source_root / "image.jpg"
    source.write_text("dummy content")
    
    dest_base = tmp_path / "dest"
    folder_format = "%Y%m%d"
    
    result = generate_destination_path(
        source, 
        source_root, 
        dest_base, 
        folder_format, 
        mode="date",
        date_source="creation"
    )
    
    assert result.name == "image.jpg"
    assert result.parent.parent == dest_base

def test_path_structure_date_modification(tmp_path):
    source_root = tmp_path / "src"
    source_root.mkdir()
    source = source_root / "image.jpg"
    source.write_text("dummy content")
    
    dest_base = tmp_path / "dest"
    folder_format = "%Y%m%d"
    
    result = generate_destination_path(
        source, 
        source_root, 
        dest_base, 
        folder_format, 
        mode="date",
        date_source="modification"
    )
    
    # Use replace(microsecond=0) to avoid flakiness
    mtime_dt = datetime.datetime.fromtimestamp(source.stat().st_mtime).replace(microsecond=0)
    mtime_str = mtime_dt.strftime(folder_format)
    expected = dest_base / mtime_str / "image.jpg"
    
    # Check that the result matches the expected date folder
    assert result.name == "image.jpg"
    assert result.parent.name == mtime_str

def test_path_structure_mirror_nested(tmp_path):
    source_root = tmp_path / "src"
    source_root.mkdir()
    # Create deeply nested structure
    subfolder = source_root / "A" / "B" / "C"
    subfolder.mkdir(parents=True)
    source = subfolder / "deep_file.jpg"
    source.write_text("data")
    
    dest_base = tmp_path / "dest"
    
    result = generate_destination_path(
        source, 
        source_root, 
        dest_base, 
        folder_format="", 
        mode="mirror"
    )
    
    expected = dest_base / "A" / "B" / "C" / "deep_file.jpg"
    assert result == expected

def test_path_structure_mirror_root(tmp_path):
    source_root = tmp_path / "src"
    source_root.mkdir()
    source = source_root / "root_file.jpg"
    source.write_text("data")
    
    dest_base = tmp_path / "dest"
    
    result = generate_destination_path(
        source, 
        source_root, 
        dest_base, 
        folder_format="", 
        mode="mirror"
    )
    
    # Should be directly under dest_base
    expected = dest_base / "root_file.jpg"
    assert result == expected

def test_get_file_date_creation_fallback(tmp_path):
    source = (tmp_path / "test.txt").resolve()
    source.write_text("data")
    
    # Use a fixed integer timestamp to avoid microsecond comparison issues
    fixed_timestamp = 1600000000.0
    
    # Create a mock that behaves like stat_result but lacks st_birthtime
    mock_stat_result = MagicMock()
    mock_stat_result.st_mtime = fixed_timestamp
    # Explicitly ensure st_birthtime access raises AttributeError
    if hasattr(mock_stat_result, "st_birthtime"):
        del mock_stat_result.st_birthtime
    
    # Mock Path.stat but only for the specific source path
    # CRITICAL: Avoid calling .resolve() inside the mock as it may trigger recursion!
    original_stat = Path.stat
    def side_effect(path_instance):
        if str(path_instance) == str(source):
            return mock_stat_result
        return original_stat(path_instance)

    with patch.object(Path, "stat", autospec=True, side_effect=side_effect):
        # Should fallback to mtime
        date = get_file_date(source, source="creation")
        assert date == datetime.datetime.fromtimestamp(fixed_timestamp)

def test_get_file_date_modification(tmp_path):
    source = tmp_path / "test.txt"
    source.write_text("data")
    
    mtime = source.stat().st_mtime
    date = get_file_date(source, source="modification")
    # Compare with a small tolerance or ignore microseconds
    assert date.replace(microsecond=0) == datetime.datetime.fromtimestamp(mtime).replace(microsecond=0)

def test_get_file_date_filename(tmp_path):
    # Test successful parsing
    source = tmp_path / "2015-12-26 15.13.52-1.jpg"
    source.write_text("data")
    
    date = get_file_date(source, source="filename", filename_date_format="%Y-%m-%d %H.%M.%S")
    assert date == datetime.datetime(2015, 12, 26, 15, 13, 52)
    
    # Test different format
    source2 = tmp_path / "IMG_20230101_120000.jpg"
    source2.write_text("data")
    date2 = get_file_date(source2, source="filename", filename_date_format="IMG_%Y%m%d_%H%M%S")
    assert date2 == datetime.datetime(2023, 1, 1, 12, 0, 0)

def test_get_file_date_filename_fallback(tmp_path):
    # Filename doesn't match format
    source = (tmp_path / "not_a_date.jpg").resolve()
    source.write_text("data")
    
    fixed_timestamp = 1600000000.0
    mock_stat_result = MagicMock()
    mock_stat_result.st_mtime = fixed_timestamp
    # Include st_birthtime to simulate a system that has it but we fall back from filename
    mock_stat_result.st_birthtime = fixed_timestamp + 100 

    original_stat = Path.stat
    def side_effect(path_instance):
        if str(path_instance) == str(source):
            return mock_stat_result
        return original_stat(path_instance)

    with patch.object(Path, "stat", autospec=True, side_effect=side_effect):
        # Should fallback to creation (which we mocked to fixed_timestamp + 100)
        date = get_file_date(source, source="filename", filename_date_format="%Y%m%d")
        assert date == datetime.datetime.fromtimestamp(fixed_timestamp + 100)

def test_get_file_date_filename_short(tmp_path):
    # Filename stem is shorter than expected format length
    source = (tmp_path / "2023.jpg").resolve()
    source.write_text("data")
    
    fixed_timestamp = 1600000000.0
    mock_stat_result = MagicMock()
    mock_stat_result.st_mtime = fixed_timestamp
    if hasattr(mock_stat_result, "st_birthtime"):
        del mock_stat_result.st_birthtime # No birthtime fallback

    original_stat = Path.stat
    def side_effect(path_instance):
        if str(path_instance) == str(source):
            return mock_stat_result
        return original_stat(path_instance)

    with patch.object(Path, "stat", autospec=True, side_effect=side_effect):
        date = get_file_date(source, source="filename", filename_date_format="%Y%m%d")
        assert date == datetime.datetime.fromtimestamp(fixed_timestamp)

def test_get_file_date_filename_invalid_type(tmp_path):
    source = (tmp_path / "20230101.jpg").resolve()
    source.write_text("data")
    
    fixed_timestamp = 1600000000.0
    mock_stat_result = MagicMock()
    mock_stat_result.st_mtime = fixed_timestamp
    if hasattr(mock_stat_result, "st_birthtime"):
        del mock_stat_result.st_birthtime

    original_stat = Path.stat
    def side_effect(path_instance):
        if str(path_instance) == str(source):
            return mock_stat_result
        return original_stat(path_instance)

    with patch.object(Path, "stat", autospec=True, side_effect=side_effect):
        # Force a fallback by passing None which causes TypeError in length check
        date = get_file_date(source, source="filename", filename_date_format=None)
        assert date == datetime.datetime.fromtimestamp(fixed_timestamp)

def test_generate_destination_path_filename(tmp_path):
    source_root = tmp_path / "src"
    source_root.mkdir()
    source = source_root / "2015-12-26 15.13.52-1.jpg"
    source.write_text("data")
    
    dest_base = tmp_path / "dest"
    folder_format = "%Y/%m/%d"
    
    result = generate_destination_path(
        source,
        source_root,
        dest_base,
        folder_format,
        mode="date",
        date_source="filename",
        filename_date_format="%Y-%m-%d %H.%M.%S"
    )
    
    assert result == dest_base / "2015/12/26" / "2015-12-26 15.13.52-1.jpg"
