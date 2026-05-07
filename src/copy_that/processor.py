import shutil
import logging
import hashlib
import time
import errno
import os
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
    retried: bool = False

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

def is_retryable_error(e: Exception) -> bool:
    """
    Determine if an OSError is transient and should be retried.
    """
    if not isinstance(e, OSError):
        return False
        
    # List of errno values that are typically transient/retryable
    retryable_errnos = {
        errno.EIO,          # Input/output error
        errno.ETIMEDOUT,     # Connection timed out
        errno.EBUSY,        # Device or resource busy
        errno.EAGAIN,       # Try again
        errno.ENODEV,       # No such device (can happen with flaky USB)
    }
    
    # Handle ECONNRESET if it's available (relevant for network mounts)
    if hasattr(errno, "ECONNRESET"):
        retryable_errnos.add(errno.ECONNRESET)
        
    return e.errno in retryable_errnos

def copy_file(
    source: Path, 
    destination: Path, 
    conflict_policy: str = "skip",
    verification_method: VerificationMethod = "none",
    verification_failure_behavior: Literal["retry", "ignore", "delete"] = "retry",
    buffer_size: int = 1024 * 1024,
    max_retries: int = 3,
    retry_base_delay: float = 1.0,
    retry_exponential_backoff: bool = True
) -> FileResult:
    """
    Copy a file from source to destination with metadata preservation and verification.
    Implements Atomic Writes (using .ct-tmp) and Robust Retries with exponential backoff.
    """
    final_destination = destination
    status = SyncStatus.COPIED
    
    try:
        bytes_to_copy = source.stat().st_size
    except OSError as e:
        err_msg = f"Source file inaccessible: {e}"
        logger.error(err_msg)
        return FileResult(SyncStatus.FAILED, source, destination, error_message=err_msg)

    if destination.exists():
        if conflict_policy == "skip":
            if verification_method == "none":
                return FileResult(SyncStatus.SKIPPED, source, destination)
            else:
                # Integrity-aware skip: Verify the existing file first
                if verify_copy(source, destination, verification_method, buffer_size=buffer_size):
                    return FileResult(SyncStatus.SKIPPED, source, destination)
                else:
                    logger.debug(f"Existing file {destination.name} failed verification. Re-copying...")
                    status = SyncStatus.OVERWRITTEN
        elif conflict_policy == "overwrite":
            status = SyncStatus.OVERWRITTEN
        elif conflict_policy == "rename":
            final_destination = get_unique_path(destination)
            status = SyncStatus.RENAMED

    # Atomic Write: Copy to a temporary file first
    temp_destination = final_destination.with_suffix(final_destination.suffix + ".ct-tmp")
    
    # Create parent directories
    final_destination.parent.mkdir(parents=True, exist_ok=True)
    
    last_error_msg = None
    retried = False

    for attempt in range(max_retries + 1):
        if attempt > 0:
            retried = True
            delay = retry_base_delay * (2 ** (attempt - 1) if retry_exponential_backoff else 1)
            logger.warning(f"Retry attempt {attempt}/{max_retries} for {source.name} after {delay:.1f}s delay...")
            time.sleep(delay)

        try:
            # Perform Copy to temp file
            with open(source, "rb") as fsrc:
                with open(temp_destination, "wb") as fdst:
                    shutil.copyfileobj(fsrc, fdst, length=buffer_size)
            
            # Preserve metadata on the temp file
            shutil.copystat(source, temp_destination)
            
            # Perform verification on the temp file
            if not verify_copy(source, temp_destination, verification_method, buffer_size=buffer_size):
                if verification_failure_behavior == "retry":
                    last_error_msg = "Verification failed"
                    temp_destination.unlink(missing_ok=True)
                    continue # Try again
                elif verification_failure_behavior == "delete":
                    temp_destination.unlink(missing_ok=True)
                    return FileResult(SyncStatus.FAILED, source, final_destination, error_message="Verification failed and file deleted")
                elif verification_failure_behavior == "ignore":
                    logger.debug(f"Verification failed for {source.name}, but ignoring per config.")
                    # Move temp to final and return success
                    os.replace(temp_destination, final_destination)
                    return FileResult(status, source, final_destination, bytes_transferred=bytes_to_copy, retried=retried)
                else:
                    temp_destination.unlink(missing_ok=True)
                    return FileResult(SyncStatus.FAILED, source, final_destination, error_message="Verification failed")

            # Success: Move temp file to final destination
            os.replace(temp_destination, final_destination)
            return FileResult(status, source, final_destination, bytes_transferred=bytes_to_copy, retried=retried)

        except Exception as e:
            last_error_msg = str(e)
            temp_destination.unlink(missing_ok=True)
            
            if is_retryable_error(e):
                logger.debug(f"Transient error copying {source.name}: {last_error_msg}")
                continue # Retry loop
            else:
                # Terminal error
                logger.error(f"Failed to copy {source} to {final_destination}: {last_error_msg}")
                return FileResult(SyncStatus.FAILED, source, final_destination, error_message=last_error_msg, retried=retried)

    # If we get here, retries were exhausted
    return FileResult(SyncStatus.FAILED, source, final_destination, error_message=f"Retries exhausted. Last error: {last_error_msg}", retried=retried)

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
