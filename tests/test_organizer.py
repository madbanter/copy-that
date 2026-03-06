import datetime
from pathlib import Path
from copy_that.organizer import generate_destination_path

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
    
    # We can't easily mock stat() creation time in a cross-platform way,
    # but we can check if it contains a date-like folder.
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

def test_path_structure_mirror(tmp_path):
    source_root = tmp_path / "src"
    source_root.mkdir()
    subfolder = source_root / "vacation" / "2023"
    subfolder.mkdir(parents=True)
    source = subfolder / "photo.jpg"
    source.write_text("data")
    
    dest_base = tmp_path / "dest"
    
    result = generate_destination_path(
        source, 
        source_root, 
        dest_base, 
        folder_format="", 
        mode="mirror"
    )
    
    expected = dest_base / "vacation" / "2023" / "photo.jpg"
    assert result == expected
