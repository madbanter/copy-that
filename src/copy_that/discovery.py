import os
import logging
from pathlib import Path
from typing import Generator, List, Set, Tuple

logger = logging.getLogger(__name__)

def discover_files(source_dir: Path, extensions: List[str]) -> Generator[Tuple[Path, int], None, None]:
    """
    Recursively discover files in the source directory that match the given extensions.
    Yields tuples of (Path, size_in_bytes).
    Uses os.scandir for performance optimization on large directory trees.
    """
    ext_set: Set[str] = {ext.lower() for ext in extensions}
    # Ensure extensions start with a dot for consistency with pathlib suffix
    normalized_exts = {ext if ext.startswith('.') else f'.{ext}' for ext in ext_set}
    
    yield from _scan_recursive(source_dir, normalized_exts)

def _scan_recursive(current_dir: Path, extensions: Set[str]) -> Generator[Tuple[Path, int], None, None]:
    """
    Internal recursive generator using os.scandir.
    """
    try:
        with os.scandir(current_dir) as entries:
            for entry in entries:
                try:
                    if entry.is_file():
                        # Get extension efficiently from entry.name
                        _, ext = os.path.splitext(entry.name)
                        if ext.lower() in extensions:
                            # Use entry.stat().st_size which is often cached by the OS during scandir
                            yield Path(entry.path), entry.stat().st_size
                    elif entry.is_dir(follow_symlinks=False):
                        yield from _scan_recursive(Path(entry.path), extensions)
                except (PermissionError, FileNotFoundError) as e:
                    logger.warning(f"Error accessing {entry.path}: {e}")
    except (PermissionError, FileNotFoundError) as e:
        logger.warning(f"Error scanning directory {current_dir}: {e}")
