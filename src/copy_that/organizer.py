import datetime
import os
import logging
from pathlib import Path
from typing import Literal

logger = logging.getLogger(__name__)

def get_file_date(
    file_path: Path, 
    source: Literal["creation", "modification", "filename"] = "creation",
    filename_date_format: str = "%Y-%m-%d %H.%M.%S"
) -> datetime.datetime:
    """
    Get the creation, modification, or filename-extracted date of a file.
    
    In 'filename' mode:
    Parses the date from the beginning of the filename stem.
    Falls back to 'creation' if parsing fails.
    
    In 'creation' mode:
    On macOS/Darwin, st_birthtime is used.
    Falls back to st_mtime if birthtime is unavailable.
    
    In 'modification' mode:
    st_mtime is used.
    """
    if source == "filename":
        try:
            # Get a sample formatted string to determine the expected length
            sample_date = datetime.datetime(2000, 1, 1, 12, 0, 0)
            expected_length = len(sample_date.strftime(filename_date_format))
            
            # Extract the relevant part of the filename stem
            stem = file_path.stem
            if len(stem) >= expected_length:
                date_str = stem[:expected_length]
                return datetime.datetime.strptime(date_str, filename_date_format)
            else:
                raise ValueError(f"Filename stem '{stem}' is shorter than expected length {expected_length}")
        except (ValueError, TypeError) as e:
            logger.warning(
                f"Could not parse date from filename '{file_path.name}' "
                f"using format '{filename_date_format}'. "
                f"Falling back to creation time. Error: {e}"
            )
            # Fall through to creation fallback
            source = "creation"

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
    date_source: Literal["creation", "modification", "filename"] = "creation",
    filename_date_format: str = "%Y-%m-%d %H.%M.%S"
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
        date = get_file_date(source_file, date_source, filename_date_format)
        subfolder_name = date.strftime(folder_format)
        return destination_base / subfolder_name / source_file.name
