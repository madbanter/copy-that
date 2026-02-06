from pathlib import Path
import datetime
from copy_that.organizer import generate_destination_path

def test_generate_destination_path():
    source = Path("test_image.jpg")
    dest_base = Path("/tmp/imports")
    folder_format = "%Y%m%d"
    
    # We can't easily mock stat() without a real file or a complex mock,
    # but we can verify the structure.
    # Note: This will use the actual file if it exists, but for a unit test
    # we should ideally use a temp file.
    pass

def test_path_structure(tmp_path):
    source = tmp_path / "image.jpg"
    source.write_text("dummy content")
    
    dest_base = tmp_path / "dest"
    folder_format = "%Y%m%d"
    
    result = generate_destination_path(source, dest_base, folder_format)
    
    today = datetime.datetime.now().strftime("%Y%m%d")
    expected = dest_base / today / "image.jpg"
    
    assert result == expected
