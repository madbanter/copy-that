import os
import logging
import fnmatch
import re
from pathlib import Path
from typing import Generator, List, Set, Tuple, Optional

logger = logging.getLogger(__name__)

class FileFilter:
    """Handles glob and regex based file/directory filtering."""
    
    def __init__(self, exclude_patterns: List[str] = None, exclude_regex: List[str] = None):
        self.exclude_patterns = exclude_patterns or []
        self.exclude_regex = [re.compile(r) for r in (exclude_regex or [])]

    def should_exclude(self, path: Path) -> bool:
        """Return True if the path matches any exclude pattern or regex."""
        name = path.name
        path_str = str(path)
        
        # Check glob patterns against the name
        for pattern in self.exclude_patterns:
            if fnmatch.fnmatch(name, pattern):
                return True
        
        # Check regex against the full path string
        for regex in self.exclude_regex:
            if regex.search(path_str):
                return True
        
        return False

def discover_files(
    source_dir: Path, 
    extensions: List[str], 
    exclude_patterns: Optional[List[str]] = None,
    exclude_regex: Optional[List[str]] = None
) -> Generator[Tuple[Path, int], None, None]:
    """
    Recursively discover files in the source directory that match the given extensions.
    Yields tuples of (Path, size_in_bytes).
    Uses os.scandir for performance optimization on large directory trees.
    """
    ext_set: Set[str] = {ext.lower() for ext in extensions}
    # Ensure extensions start with a dot for consistency with pathlib suffix
    normalized_exts = {ext if ext.startswith('.') else f'.{ext}' for ext in ext_set}
    
    file_filter = FileFilter(exclude_patterns, exclude_regex)
    
    yield from _scan_recursive(source_dir, normalized_exts, file_filter)

def _scan_recursive(current_dir: Path, extensions: Set[str], file_filter: FileFilter) -> Generator[Tuple[Path, int], None, None]:
    """
    Internal recursive generator using os.scandir.
    """
    try:
        with os.scandir(current_dir) as entries:
            for entry in entries:
                try:
                    entry_path = Path(entry.path)
                    if file_filter.should_exclude(entry_path):
                        continue
                        
                    if entry.is_file():
                        # Get extension efficiently from entry.name
                        _, ext = os.path.splitext(entry.name)
                        if ext.lower() in extensions:
                            # Use entry.stat().st_size which is often cached by the OS during scandir
                            yield entry_path, entry.stat().st_size
                    elif entry.is_dir(follow_symlinks=False):
                        yield from _scan_recursive(entry_path, extensions, file_filter)
                except (PermissionError, FileNotFoundError) as e:
                    logger.warning(f"Error accessing {entry.path}: {e}")
    except (PermissionError, FileNotFoundError) as e:
        logger.warning(f"Error scanning directory {current_dir}: {e}")
