import shutil
import logging
import hashlib
import time
import errno
import os
import threading
from pathlib import Path
from typing import Optional, Literal, Callable
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
        # Quick size check first: if sizes differ, checksums will definitely differ.
        # This saves expensive hashing on truncated/failed copies.
        if source.stat().st_size != destination.stat().st_size:
            logger.warning(
                f"Size mismatch during verification for {destination.name}: "
                f"source={source.stat().st_size}, dest={destination.stat().st_size}"
            )
            return False

        if method == "size":
            return True
            
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

class ProgressFileWrapper:
    """Wraps a file object to intercept read() calls and report progress."""
    def __init__(self, file_obj, callback: Callable[[int], None]):
        self.file_obj = file_obj
        self.callback = callback

    def read(self, size=-1):
        data = self.file_obj.read(size)
        if data and self.callback:
            self.callback(len(data))
        return data

    def __getattr__(self, name):
        """Pass through other attributes/methods to the underlying file object."""
        return getattr(self.file_obj, name)

def copy_file(
    source: Path, 
    destination: Path, 
    conflict_policy: str = "skip",
    verification_method: VerificationMethod = "none",
    verification_failure_behavior: Literal["retry", "ignore", "delete"] = "retry",
    buffer_size: int = 1024 * 1024,
    max_retries: int = 3,
    retry_base_delay: float = 1.0,
    retry_exponential_backoff: bool = True,
    progress_callback: Optional[Callable[[int], None]] = None,
    allocated_paths: Optional[set] = None,
    allocated_lock: Optional[threading.Lock] = None,
    active_temp_files: Optional[set] = None,
    active_temp_lock: Optional[threading.Lock] = None
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

    # Resolve destination path under the allocation lock to prevent race conditions
    has_lock = False
    if allocated_lock is not None:
        allocated_lock.acquire()
        has_lock = True
        
    try:
        dest_exists = final_destination.exists() or (allocated_paths is not None and final_destination in allocated_paths)
        if dest_exists:
            if conflict_policy == "skip":
                if final_destination.exists():
                    if verification_method == "none":
                        return FileResult(SyncStatus.SKIPPED, source, final_destination)
                    else:
                        # Release lock for expensive checksum checking
                        if has_lock:
                            allocated_lock.release()
                            has_lock = False
                        if verify_copy(source, final_destination, verification_method, buffer_size=buffer_size):
                            return FileResult(SyncStatus.SKIPPED, source, final_destination)
                        else:
                            logger.debug(f"Existing file {final_destination.name} failed verification. Re-copying...")
                            status = SyncStatus.OVERWRITTEN
                else:
                    return FileResult(SyncStatus.SKIPPED, source, final_destination)
            elif conflict_policy == "overwrite":
                status = SyncStatus.OVERWRITTEN
            elif conflict_policy == "rename":
                # get_unique_path resolves unique path against both disk and active allocations
                final_destination = get_unique_path(final_destination, allocated_paths, lock=None)
                status = SyncStatus.RENAMED

        # If lock was released during verification, re-acquire to add final path to registry
        if allocated_lock is not None and not has_lock:
            allocated_lock.acquire()
            has_lock = True

        if allocated_paths is not None:
            allocated_paths.add(final_destination)
    finally:
        if has_lock:
            allocated_lock.release()

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

        # Register active temporary file for graceful interrupt cleanup
        if active_temp_files is not None:
            if active_temp_lock is not None:
                with active_temp_lock:
                    active_temp_files.add(temp_destination)
            else:
                active_temp_files.add(temp_destination)

        try:
            # Perform Copy to temp file
            with open(source, "rb") as fsrc:
                with open(temp_destination, "wb") as fdst:
                    fsrc_proxy = ProgressFileWrapper(fsrc, progress_callback) if progress_callback else fsrc
                    shutil.copyfileobj(fsrc_proxy, fdst, length=buffer_size)
            
            # Preserve metadata on the temp file
            try:
                shutil.copystat(source, temp_destination)
            except OSError as e:
                logger.debug(f"copystat failed for {source.name} -> {temp_destination.name}: {e}. Trying utime fallback...")
                try:
                    stat_val = source.stat()
                    os.utime(temp_destination, (stat_val.st_atime, stat_val.st_mtime))
                except OSError as utime_err:
                    logger.warning(f"Could not preserve timestamps for {source.name}: {utime_err}")
            
            # Perform verification on the temp file
            if not verify_copy(source, temp_destination, verification_method, buffer_size=buffer_size):
                if verification_failure_behavior == "retry":
                    last_error_msg = "Verification failed"
                    temp_destination.unlink(missing_ok=True)
                    if active_temp_files is not None:
                        if active_temp_lock is not None:
                            with active_temp_lock:
                                active_temp_files.discard(temp_destination)
                        else:
                            active_temp_files.discard(temp_destination)
                    continue # Try again
                elif verification_failure_behavior == "delete":
                    temp_destination.unlink(missing_ok=True)
                    if active_temp_files is not None:
                        if active_temp_lock is not None:
                            with active_temp_lock:
                                active_temp_files.discard(temp_destination)
                        else:
                            active_temp_files.discard(temp_destination)
                    return FileResult(SyncStatus.FAILED, source, final_destination, error_message="Verification failed and file deleted")
                elif verification_failure_behavior == "ignore":
                    logger.debug(f"Verification failed for {source.name}, but ignoring per config.")
                    # Move temp to final and return success
                    os.replace(temp_destination, final_destination)
                    if active_temp_files is not None:
                        if active_temp_lock is not None:
                            with active_temp_lock:
                                active_temp_files.discard(temp_destination)
                        else:
                            active_temp_files.discard(temp_destination)
                    return FileResult(status, source, final_destination, bytes_transferred=bytes_to_copy, retried=retried)
                else:
                    temp_destination.unlink(missing_ok=True)
                    if active_temp_files is not None:
                        if active_temp_lock is not None:
                            with active_temp_lock:
                                active_temp_files.discard(temp_destination)
                        else:
                            active_temp_files.discard(temp_destination)
                    return FileResult(SyncStatus.FAILED, source, final_destination, error_message="Verification failed")

            # Success: Move temp file to final destination
            os.replace(temp_destination, final_destination)
            if active_temp_files is not None:
                if active_temp_lock is not None:
                    with active_temp_lock:
                        active_temp_files.discard(temp_destination)
                else:
                    active_temp_files.discard(temp_destination)
            return FileResult(status, source, final_destination, bytes_transferred=bytes_to_copy, retried=retried)

        except Exception as e:
            last_error_msg = str(e)
            temp_destination.unlink(missing_ok=True)
            if active_temp_files is not None:
                if active_temp_lock is not None:
                    with active_temp_lock:
                        active_temp_files.discard(temp_destination)
                else:
                    active_temp_files.discard(temp_destination)
            
            if is_retryable_error(e):
                logger.debug(f"Transient error copying {source.name}: {last_error_msg}")
                continue # Retry loop
            else:
                # Terminal error
                return FileResult(SyncStatus.FAILED, source, final_destination, error_message=last_error_msg, retried=retried)

    # If we get here, retries were exhausted
    return FileResult(SyncStatus.FAILED, source, final_destination, error_message=f"Retries exhausted. Last error: {last_error_msg}", retried=retried)

def get_unique_path(path: Path, allocated_paths: Optional[set] = None, lock: Optional[threading.Lock] = None) -> Path:
    """
    If path exists or is allocated, append a counter to the filename until a unique path is found.
    Example: image.jpg -> image_1.jpg -> image_2.jpg
    """
    counter = 1
    stem = path.stem
    suffix = path.suffix
    parent = path.parent
    
    new_path = path
    
    def path_exists_or_allocated(p: Path) -> bool:
        if p.exists():
            return True
        if allocated_paths is not None:
            return p in allocated_paths
        return False

    if lock is not None:
        with lock:
            while path_exists_or_allocated(new_path):
                new_path = parent / f"{stem}_{counter}{suffix}"
                counter += 1
            if allocated_paths is not None:
                allocated_paths.add(new_path)
    else:
        while path_exists_or_allocated(new_path):
            new_path = parent / f"{stem}_{counter}{suffix}"
            counter += 1
        if allocated_paths is not None:
            allocated_paths.add(new_path)
            
    return new_path
