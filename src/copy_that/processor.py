import shutil
import logging
import hashlib
from pathlib import Path
from typing import Optional, Literal

logger = logging.getLogger(__name__)

def calculate_checksum(path: Path, algorithm: str, buffer_size: int = 1024 * 1024) -> str:
    """
    Calculate the checksum of a file using the specified algorithm (md5 or sha1).
    Uses hashlib.file_digest in Python 3.11+ for performance.
    """
    hash_func_name = algorithm.lower()
    
    # Python 3.11+ optimized way
    if hasattr(hashlib, "file_digest"):
        with open(path, "rb") as f:
            digest = hashlib.file_digest(f, hash_func_name)
            return digest.hexdigest()
    
    # Fallback for Python 3.10
    hash_func = hashlib.md5() if hash_func_name == "md5" else hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(buffer_size), b""):
            hash_func.update(chunk)
    return hash_func.hexdigest()

def verify_copy(
    source: Path, 
    destination: Path, 
    method: Literal["none", "size", "md5", "sha1"],
    buffer_size: int = 1024 * 1024
) -> bool:
    """
    Verify that the destination file matches the source file based on the selected method.
    """
    if method == "none":
        return True
    
    if method == "size":
        source_size = source.stat().st_size
        dest_size = destination.stat().st_size
        if source_size != dest_size:
            logger.error(f"Verification failed: Size mismatch for {destination.name} (Source: {source_size}, Dest: {dest_size})")
            return False
        return True
    
    if method in ("md5", "sha1"):
        source_hash = calculate_checksum(source, method, buffer_size=buffer_size)
        dest_hash = calculate_checksum(destination, method, buffer_size=buffer_size)
        if source_hash != dest_hash:
            logger.error(f"Verification failed: {method.upper()} mismatch for {destination.name}")
            return False
        return True
    
    return True

def copy_file(
    source: Path, 
    destination: Path, 
    conflict_policy: str = "skip",
    verification_method: Literal["none", "size", "md5", "sha1"] = "none",
    verification_failure_behavior: Literal["retry", "ignore", "delete"] = "retry",
    buffer_size: int = 1024 * 1024,
    _retry_count: int = 0
) -> bool:
    """
    Copy a file from source to destination with metadata preservation and verification.
    Returns True if the file was copied and verified, False if skipped or verification failed.
    """
    if destination.exists():
        if conflict_policy == "skip":
            if verification_method == "none":
                logger.info(f"Skipping existing file: {destination.name}")
                return False
            else:
                # Integrity-aware skip: Verify the existing file first
                if verify_copy(source, destination, verification_method, buffer_size=buffer_size):
                    logger.info(f"Skipping (already verified): {destination.name}")
                    return False
                else:
                    logger.warning(f"Existing file {destination.name} failed verification. Re-copying...")
                    # Proceed to copy (overwrite)
        elif conflict_policy == "overwrite":
            logger.info(f"Overwriting file: {destination.name}")
        elif conflict_policy == "rename":
            destination = get_unique_path(destination)
            logger.info(f"Renaming to: {destination.name}")

    # Create parent directories if they don't exist
    destination.parent.mkdir(parents=True, exist_ok=True)
    
    try:
        # Optimized Buffered I/O using copyfileobj
        with open(source, "rb") as fsrc:
            with open(destination, "wb") as fdst:
                shutil.copyfileobj(fsrc, fdst, length=buffer_size)
        
        # Preserve metadata (mtime, atime, flags, etc.)
        shutil.copystat(source, destination)
        
    except Exception as e:
        logger.error(f"Failed to copy {source} to {destination}: {e}")
        return False

    # Perform verification
    if not verify_copy(source, destination, verification_method, buffer_size=buffer_size):
        if verification_failure_behavior == "retry" and _retry_count < 1:
            logger.info(f"Retrying copy for {source.name}...")
            return copy_file(
                source, 
                destination, 
                conflict_policy="overwrite", # Use overwrite during retry
                verification_method=verification_method,
                verification_failure_behavior=verification_failure_behavior,
                buffer_size=buffer_size,
                _retry_count=_retry_count + 1
            )
        elif verification_failure_behavior == "delete":
            logger.warning(f"Deleting corrupted destination file: {destination}")
            destination.unlink(missing_ok=True)
            return False
        elif verification_failure_behavior == "ignore":
            logger.warning(f"Verification failed for {destination.name}, but ignoring per config.")
            return True
        else:
            return False

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
