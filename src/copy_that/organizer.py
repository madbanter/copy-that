import datetime
import os
from pathlib import Path
from typing import Literal

def get_file_date(file_path: Path, source: Literal["creation", "modification"] = "creation") -> datetime.datetime:
    """
    Get the creation or modification date of a file.
    
    In 'creation' mode:
    On macOS/Darwin, st_birthtime is used.
    Falls back to st_mtime if birthtime is unavailable.
    
    In 'modification' mode:
    st_mtime is used.
    """
    stat = file_path.stat()
    
    if source == "modification":
        timestamp = stat.st_mtime
    else:
        # Default to creation
        try:
            # macOS/Darwin specific creation time
            timestamp = stat.st_birthtime
        except AttributeError:
            # Fallback to modification time for other systems
            timestamp = stat.st_mtime
    
    return datetime.datetime.fromtimestamp(timestamp)

def generate_destination_path(
    source_file: Path,
    source_root: Path,
    destination_base: Path,
    folder_format: str,
    mode: Literal["date", "mirror"] = "date",
    date_source: Literal["creation", "modification"] = "creation"
) -> Path:
    """
    Generate the destination path based on the selected mode.
    
    In 'date' mode, subfolders are created based on the file's date.
    In 'mirror' mode, the relative path from the source_root is preserved.
    """
    if mode == "mirror":
        relative_path = source_file.relative_to(source_root)
        return destination_base / relative_path
    else:
        # 'date' mode
        date = get_file_date(source_file, date_source)
        subfolder_name = date.strftime(folder_format)
        return destination_base / subfolder_name / source_file.name
