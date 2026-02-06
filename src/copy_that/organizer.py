import datetime
import os
from pathlib import Path

def get_creation_date(file_path: Path) -> datetime.datetime:
    """
    Get the creation date of a file. 
    On macOS/Darwin, st_birthtime is used.
    Falls back to st_mtime if birthtime is unavailable.
    """
    stat = file_path.stat()
    try:
        # macOS/Darwin specific creation time
        timestamp = stat.st_birthtime
    except AttributeError:
        # Fallback to modification time for other systems
        timestamp = stat.st_mtime
    
    return datetime.datetime.fromtimestamp(timestamp)

def generate_destination_path(
    source_file: Path, 
    destination_base: Path, 
    folder_format: str
) -> Path:
    """
    Generate the destination path based on creation date.
    """
    creation_date = get_creation_date(source_file)
    subfolder_name = creation_date.strftime(folder_format)
    return destination_base / subfolder_name / source_file.name
