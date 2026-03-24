import shutil
import logging
import hashlib
from pathlib import Path
from typing import Optional, Literal
from enum import Enum
from dataclasses import dataclass

from copy_that.config import VerificationMethod, SUPPORTED_VERIFICATION_METHODS

logger = logging.getLogger(__name__)

class SyncStatus(Enum):
    COPIED = "copied"
    SKIPPED = "skipped"
    FAILED = "failed"
    OVERWRITTEN = "overwritten"
    RENAMED = "renamed"

@dataclass
class FileResult:
    status: SyncStatus
    source_path: Path
    destination_path: Path
    bytes_transferred: int = 0
    error_message: Optional[str] = None

def calculate_checksum(path: Path, algorithm: str, buffer_size: int = 1024 * 1024) -> str:
    """
    Calculate the checksum of a file using the specified algorithm.
    Utilizes hashlib.file_digest (Python 3.11+) if available for performance.
    """
    if hasattr(hashlib, "file_digest"):
        with open(path, "rb") as f:
            return hashlib.file_digest(f, algorithm).hexdigest()
    
    # Fallback for Python < 3.11
    hasher = hashlib.new(algorithm)
    with open(path, "rb") as f:
        while True:
            chunk = f.read(buffer_size)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()

def verify_copy(
    source: Path, 
    destination: Path, 
    method: VerificationMethod = "none",
    buffer_size: int = 1024 * 1024
) -> bool:
    """
    Verify that the destination file matches the source file using the specified method.
    Returns True if verification passes, False if it fails or if verification cannot be performed.
    """
    if method == "none":
        return True
    
    if method not in SUPPORTED_VERIFICATION_METHODS:
        logger.error(f"Unknown verification method: {method}")
        return False

    try:
        if method == "size":
            return source.stat().st_size == destination.stat().st_size
            
        source_checksum = calculate_checksum(source, method, buffer_size=buffer_size)
        dest_checksum = calculate_checksum(destination, method, buffer_size=buffer_size)
        
        return source_checksum == dest_checksum
    except (ValueError, OSError) as e:
        logger.error(f"Could not verify {destination.name} using {method}: {e}")
        return False # Fail-closed: Verification failed to complete, so assume the copy is potentially invalid

def copy_file(
    source: Path, 
    destination: Path, 
    conflict_policy: str = "skip",
    verification_method: VerificationMethod = "none",
    verification_failure_behavior: Literal["retry", "ignore", "delete"] = "retry",
    buffer_size: int = 1024 * 1024,
    _retry_count: int = 0
) -> FileResult:
    """
    Copy a file from source to destination with metadata preservation and verification.
    Returns a FileResult object detailing the outcome.
    """
    final_destination = destination
    status = SyncStatus.COPIED
    bytes_to_copy = source.stat().st_size

    if destination.exists():
        if conflict_policy == "skip":
            if verification_method == "none":
                logger.warning(f"Skipping existing file: {destination.name}")
                return FileResult(SyncStatus.SKIPPED, source, destination)
            else:
                # Integrity-aware skip: Verify the existing file first
                if verify_copy(source, destination, verification_method, buffer_size=buffer_size):
                    logger.warning(f"Skipping (verification successful): {destination.name}")
                    return FileResult(SyncStatus.SKIPPED, source, destination)
                else:
                    logger.warning(f"Existing file {destination.name} failed verification. Re-copying...")
                    status = SyncStatus.OVERWRITTEN
                    # Proceed to copy (overwrite)
        elif conflict_policy == "overwrite":
            logger.warning(f"Overwriting file: {destination.name}")
            status = SyncStatus.OVERWRITTEN
        elif conflict_policy == "rename":
            final_destination = get_unique_path(destination)
            logger.warning(f"Renaming to: {final_destination.name}")
            status = SyncStatus.RENAMED

    # Create parent directories if they don't exist
    final_destination.parent.mkdir(parents=True, exist_ok=True)
    
    try:
        # Optimized Buffered I/O using copyfileobj
        with open(source, "rb") as fsrc:
            with open(final_destination, "wb") as fdst:
                shutil.copyfileobj(fsrc, fdst, length=buffer_size)
        
        # Preserve metadata (mtime, atime, flags, etc.)
        shutil.copystat(source, final_destination)
        
    except Exception as e:
        err_msg = str(e)
        logger.error(f"Failed to copy {source} to {final_destination}: {err_msg}")
        return FileResult(SyncStatus.FAILED, source, final_destination, error_message=err_msg)

    # Perform verification
    if not verify_copy(source, final_destination, verification_method, buffer_size=buffer_size):
        if verification_failure_behavior == "retry" and _retry_count < 1:
            logger.warning(f"Retrying copy for {source.name}...")
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
            logger.error(f"Deleting corrupted destination file: {final_destination}")
            final_destination.unlink(missing_ok=True)
            return FileResult(SyncStatus.FAILED, source, final_destination, error_message="Verification failed and file deleted")
        elif verification_failure_behavior == "ignore":
            logger.warning(f"Verification failed for {final_destination.name}, but ignoring per config.")
            return FileResult(status, source, final_destination, bytes_transferred=bytes_to_copy)
        else:
            return FileResult(SyncStatus.FAILED, source, final_destination, error_message="Verification failed")

    return FileResult(status, source, final_destination, bytes_transferred=bytes_to_copy)

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
