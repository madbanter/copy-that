import logging
import sys
import shutil
import time
from pathlib import Path
from typing import Iterable, Optional, List
from concurrent.futures import ThreadPoolExecutor, as_completed
from logging.handlers import RotatingFileHandler

import typer
from typing_extensions import Annotated

from copy_that.config import merge_config, Config
from copy_that.discovery import discover_files
from copy_that.organizer import generate_destination_path
from copy_that.processor import copy_file, SyncStatus, FileResult

app = typer.Typer(help="Copy and organize files from source to destination.")
logger = logging.getLogger("copy_that")

class OutputFilter(logging.Filter):
    """
    Filter to control console output verbosity.
    """
    def __init__(self, verbosity: str):
        super().__init__()
        self.verbosity = verbosity

    def filter(self, record: logging.LogRecord) -> bool:
        # 1. Summary report and critical errors always show
        msg = record.getMessage()
        if msg.startswith("-") or msg.startswith("Sync Summary") or msg.startswith("Total Files") or record.levelno >= logging.ERROR:
            return True
            
        # 2. Apply verbosity levels
        if self.verbosity == "minimal":
            return record.levelno >= logging.ERROR
        elif self.verbosity == "normal":
            # Normal shows INFO and above (standard behavior)
            return record.levelno >= logging.INFO
        
        # verbose shows everything including DEBUG
        return True

def format_bytes(size: int) -> str:
    """Format bytes into human-readable string."""
    if size == 0:
        return "0.00 B"
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024:
            return f"{size:.2f} {unit}"
        size /= 1024
    return f"{size:.2f} PB"

def print_summary(results: List[FileResult], elapsed_time: float):
    """Print a detailed summary of the sync operation."""
    total_files = len(results)
    copied = [r for r in results if r.status in (SyncStatus.COPIED, SyncStatus.OVERWRITTEN, SyncStatus.RENAMED)]
    skipped = [r for r in results if r.status == SyncStatus.SKIPPED]
    failed = [r for r in results if r.status == SyncStatus.FAILED]
    
    total_bytes = sum(r.bytes_transferred for r in results)
    speed = total_bytes / elapsed_time if elapsed_time > 0 else 0
    
    # Use logger.info for consistency, the filter will allow these through
    logger.info("-" * 40)
    logger.info("Sync Summary")
    logger.info("-" * 40)
    logger.info(f"Total Files Processed: {total_files}")
    logger.info(f"  - Copied:            {len(copied)}")
    logger.info(f"  - Skipped:           {len(skipped)}")
    logger.info(f"  - Failed:            {len(failed)}")
    logger.info(f"Total Data:            {format_bytes(total_bytes)}")
    logger.info(f"Elapsed Time:          {elapsed_time:.2f} seconds")
    if total_bytes > 0:
        logger.info(f"Average Speed:         {format_bytes(int(speed))}/s")
    logger.info("-" * 40)
    
    if failed:
        logger.error("Failures:")
        for r in failed:
            logger.error(f"  - {r.source_path.name}: {r.error_message}")
        logger.info("-" * 40)

def perform_space_check(source_files: Iterable[Path], config: Config) -> None:
    """
    Perform a 'Best Effort' disk space check before copying.
    If conflict_policy is 'skip', it ignores files that already exist at the destination.
    Note: This consumes the provided iterable.
    """
    total_size_needed = 0
    for source_file in source_files:
        dest_file = generate_destination_path(
            source_file,
            config.source_directory,
            config.destination_base,
            config.folder_format,
            config.organization_mode,
            config.date_source,
            config.filename_date_format
        )
        
        if config.conflict_policy == "skip" and dest_file.exists():
            continue
            
        total_size_needed += source_file.stat().st_size

    check_path = config.destination_base
    while not check_path.exists() and check_path.parent != check_path:
        check_path = check_path.parent

    free_space = shutil.disk_usage(check_path).free
    
    if total_size_needed > free_space:
        mb = 1024 * 1024
        logger.warning(
            f"Possible insufficient disk space! "
            f"Required: {total_size_needed / mb:.2f} MB, "
            f"Available: {free_space / mb:.2f} MB"
        )

def process_single_file(source_file: Path, config: Config) -> FileResult:
    """
    Generate path and copy a single file. Returns FileResult.
    """
    dest_file = generate_destination_path(
        source_file,
        config.source_directory,
        config.destination_base,
        config.folder_format,
        config.organization_mode,
        config.date_source,
        config.filename_date_format
    )

    result = copy_file(
        source_file, 
        dest_file, 
        config.conflict_policy, 
        config.verification_method,
        config.verification_failure_behavior,
        buffer_size=config.buffer_size
    )
    
    # Success logs are INFO, filter handles them
    if result.status == SyncStatus.COPIED:
        logger.info(f"Copied {source_file.name} -> {result.destination_path.relative_to(config.destination_base.parent)}")
    elif result.status == SyncStatus.FAILED:
        # Failed logs are already handled inside copy_file (ERROR)
        pass
    else:
        # Renamed, Overwritten, Skipped are already handled inside copy_file (WARNING)
        pass
    
    return result

@app.command()
def sync(
    config_path: Annotated[Optional[Path], typer.Option("--config", "-c", help="Path to config file")] = None,
    source: Annotated[Optional[Path], typer.Option("--source", "-s", help="Source directory")] = None,
    dest: Annotated[Optional[Path], typer.Option("--dest", "-d", help="Destination base directory")] = None,
    mode: Annotated[Optional[str], typer.Option("--mode", help="Organization mode (date, mirror)")] = None,
    format: Annotated[Optional[str], typer.Option("--format", help="Folder format for date mode")] = None,
    date_source: Annotated[Optional[str], typer.Option("--date-source", help="Date source (creation, modification, filename)")] = None,
    filename_date_format: Annotated[Optional[str], typer.Option("--filename-date-format", help="Date format in filename (for date-source=filename)")] = None,
    extensions: Annotated[Optional[List[str]], typer.Option("--ext", help="Include extensions (can be repeated)")] = None,
    conflict: Annotated[Optional[str], typer.Option("--conflict", help="Conflict policy (skip, overwrite, rename)")] = None,
    verify: Annotated[Optional[str], typer.Option("--verify", help="Verification method (none, size, md5, sha1)")] = None,
    verify_behavior: Annotated[Optional[str], typer.Option("--verify-behavior", help="Verification failure behavior (retry, ignore, delete)")] = None,
    space_check: Annotated[Optional[bool], typer.Option("--space-check/--no-space-check", help="Enable/disable pre-sync space check")] = None,
    workers: Annotated[Optional[int], typer.Option("--workers", help="Max workers for concurrent copying")] = None,
    buffer_size: Annotated[Optional[int], typer.Option("--buffer-size", help="Buffer size in bytes for copying and hashing")] = None,
    output_verbosity: Annotated[Optional[str], typer.Option("--verbosity", help="Output verbosity (minimal, normal, verbose)")] = None,
    log_file: Annotated[Optional[Path], typer.Option("--log-file", help="Path to audit log file (records everything)")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Show what would be copied without actually copying")] = False,
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Shortcut for --verbosity verbose")] = False,
):
    """
    Sync and organize files from source to destination.
    """
    # Merge CLI options into a single config object
    cli_overrides = {
        "source_directory": source,
        "destination_base": dest,
        "organization_mode": mode,
        "folder_format": format,
        "date_source": date_source,
        "filename_date_format": filename_date_format,
        "include_extensions": extensions,
        "conflict_policy": conflict,
        "verification_method": verify,
        "verification_failure_behavior": verify_behavior,
        "pre_sync_space_check": space_check,
        "max_workers": workers,
        "buffer_size": buffer_size,
        "output_verbosity": "verbose" if verbose else output_verbosity,
        "log_file": log_file,
    }

    try:
        config = merge_config(config_path, **cli_overrides)
    except Exception as e:
        # Fallback logging if config fails
        logging.basicConfig(level=logging.ERROR)
        logging.error(f"Configuration error: {e}")
        sys.exit(1)

    # Advanced Logging Setup
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG) # Allow everything through to handlers
    
    # Clear existing handlers if any
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # 1. Console Handler
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    console_handler.addFilter(OutputFilter(config.output_verbosity))
    root_logger.addHandler(console_handler)

    # 2. Optional Audit File Handler
    if config.log_file:
        try:
            config.log_file.parent.mkdir(parents=True, exist_ok=True)
            file_handler = RotatingFileHandler(
                config.log_file,
                maxBytes=config.max_log_size,
                backupCount=config.log_backup_count
            )
            file_handler.setLevel(logging.DEBUG)
            file_handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
            root_logger.addHandler(file_handler)
            logger.debug(f"Audit log initialized at {config.log_file}")
        except Exception as e:
            logger.error(f"Could not initialize log file: {e}")

    logger.info(f"Source: {config.source_directory}")
    logger.info(f"Destination: {config.destination_base}")
    logger.info(f"Mode: {config.organization_mode}")
    
    if not config.source_directory.exists():
        logger.error(f"Source directory does not exist: {config.source_directory}")
        sys.exit(1)

    if config.pre_sync_space_check:
        logger.info("Performing pre-sync disk space check...")
        space_check_generator = discover_files(config.source_directory, config.include_extensions)
        perform_space_check(space_check_generator, config)

    # Discover files
    files_to_sync = list(discover_files(config.source_directory, config.include_extensions))
    results: List[FileResult] = []
    start_time = time.perf_counter()

    if dry_run:
        from copy_that.processor import verify_copy, get_unique_path
        for source_file in files_to_sync:
            dest_file = generate_destination_path(
                source_file, 
                config.source_directory, 
                config.destination_base, 
                config.folder_format,
                config.organization_mode,
                config.date_source,
                config.filename_date_format
            )
            
            status = SyncStatus.COPIED
            bytes_transferred = source_file.stat().st_size
            action = "copy"
            level = logging.INFO
            
            if dest_file.exists():
                level = logging.WARNING
                if config.conflict_policy == "skip":
                    if config.verification_method == "none":
                        action = "skip (exists)"
                        status = SyncStatus.SKIPPED
                        bytes_transferred = 0
                    else:
                        if verify_copy(source_file, dest_file, config.verification_method, buffer_size=config.buffer_size):
                            action = "skip (verification successful)"
                            status = SyncStatus.SKIPPED
                            bytes_transferred = 0
                        else:
                            action = "overwrite (failed verification)"
                            status = SyncStatus.OVERWRITTEN
                elif config.conflict_policy == "overwrite":
                    action = "overwrite"
                    status = SyncStatus.OVERWRITTEN
                elif config.conflict_policy == "rename":
                    unique_dest = get_unique_path(dest_file)
                    action = f"rename to {unique_dest.name}"
                    status = SyncStatus.RENAMED
                    dest_file = unique_dest
            
            logger.log(level, f"[DRY RUN] {action.capitalize()}: {source_file.name} -> {dest_file.relative_to(config.destination_base.parent)}")
            results.append(FileResult(status, source_file, dest_file, bytes_transferred=bytes_transferred))
    else:
        # Concurrent copying
        with ThreadPoolExecutor(max_workers=config.max_workers) as executor:
            future_to_file = {
                executor.submit(process_single_file, source_file, config): source_file 
                for source_file in files_to_sync
            }
            
            for future in as_completed(future_to_file):
                results.append(future.result())

    end_time = time.perf_counter()
    print_summary(results, end_time - start_time)

def main():
    app()

if __name__ == "__main__":
    main()
