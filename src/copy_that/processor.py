import shutil
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

def copy_file(
    source: Path, 
    destination: Path, 
    conflict_policy: str = "skip"
) -> bool:
    """
    Copy a file from source to destination with metadata preservation.
    Returns True if the file was copied, False if skipped.
    """
    if destination.exists():
        if conflict_policy == "skip":
            logger.info(f"Skipping existing file: {destination.name}")
            return False
        elif conflict_policy == "overwrite":
            logger.info(f"Overwriting file: {destination.name}")
        elif conflict_policy == "rename":
            destination = get_unique_path(destination)
            logger.info(f"Renaming to: {destination.name}")

    # Create parent directories if they don't exist
    destination.parent.mkdir(parents=True, exist_ok=True)
    
    # shutil.copy2 preserves metadata (mtime, atime, flags, etc.)
    shutil.copy2(source, destination)
    return True

def get_unique_path(path: Path) -> Path:
    """
    If path exists, append a counter to the filename until a unique path is found.
    Example: image.jpg -> image_1.jpg -> image_2.jpg
    """
    counter = 1
    stem = path.stem
    suffix = path.suffix
    parent = path.parent
    
    new_path = path
    while new_path.exists():
        new_path = parent / f"{stem}_{counter}{suffix}"
        counter += 1
    return new_path
