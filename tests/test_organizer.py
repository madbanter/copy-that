import datetime
from pathlib import Path
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
    
    mtime = datetime.datetime.fromtimestamp(source.stat().st_mtime).strftime(folder_format)
    expected = dest_base / mtime / "image.jpg"
    assert result == expected

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

def test_get_file_date_creation_fallback(tmp_path, monkeypatch):
    source = tmp_path / "test.txt"
    source.write_text("data")
    
    # Simulate a system without st_birthtime (like most Linux systems)
    import os
    original_stat = Path.stat
    
    class MockStat:
        def __init__(self, st_mtime):
            self.st_mtime = st_mtime
            # No st_birthtime attribute here
    
    # We monkeypatch the stat call on the Path object
    # Actually, it's easier to mock the get_file_date internal try/except
    # But let's mock the stat result instead.
    mtime = source.stat().st_mtime
    monkeypatch.setattr(Path, "stat", lambda self: MockStat(mtime))
    
    # Should fallback to mtime
    date = get_file_date(source, source="creation")
    assert date == datetime.datetime.fromtimestamp(mtime)

def test_get_file_date_modification(tmp_path):
    source = tmp_path / "test.txt"
    source.write_text("data")
    
    mtime = source.stat().st_mtime
    date = get_file_date(source, source="modification")
    assert date == datetime.datetime.fromtimestamp(mtime)
