from pathlib import Path
from typing import Generator, List, Set

def discover_files(source_dir: Path, extensions: List[str]) -> Generator[Path, None, None]:
    """
    Recursively discover files in the source directory that match the given extensions.
    """
    ext_set: Set[str] = {ext.lower() for ext in extensions}
    
    # Ensure extensions start with a dot for consistency with pathlib suffix
    normalized_exts = {ext if ext.startswith('.') else f'.{ext}' for ext in ext_set}

    for path in source_dir.rglob("*"):
        if path.is_file() and path.suffix.lower() in normalized_exts:
            yield path
