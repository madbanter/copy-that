import argparse
import logging
import sys
import shutil
from pathlib import Path
from typing import Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed

from copy_that.config import load_config, Config
from copy_that.discovery import discover_files
from copy_that.organizer import generate_destination_path
from copy_that.processor import copy_file

logger = logging.getLogger(__name__)

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
            config.date_source
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

def process_single_file(source_file: Path, config: Config) -> bool:
    """
    Generate path and copy a single file. Returns True if successfully copied.
    """
    dest_file = generate_destination_path(
        source_file,
        config.source_directory,
        config.destination_base,
        config.folder_format,
        config.organization_mode,
        config.date_source
    )

    if copy_file(
        source_file, 
        dest_file, 
        config.conflict_policy, 
        config.verification_method,
        config.verification_failure_behavior
    ):
        logger.info(f"Copied {source_file.name} -> {dest_file.relative_to(config.destination_base.parent)}")
        return True
    return False

def main():
    parser = argparse.ArgumentParser(description="Copy and organize files from source to destination.")
    parser.add_argument("--config", type=Path, default=Path("config.yaml"), help="Path to config file")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be copied without actually copying")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")

    args = parser.parse_args()

    # Setup logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=log_level, format="%(levelname)s: %(message)s")

    try:
        config = load_config(args.config)
    except Exception as e:
        logger.error(f"Failed to load config: {e}")
        sys.exit(1)

    logger.info(f"Source: {config.source_directory}")
    logger.info(f"Destination: {config.destination_base}")
    logger.info(f"Mode: {config.organization_mode}")
    if config.organization_mode == "date":
        logger.info(f"Date Source: {config.date_source}")

    if not config.source_directory.exists():
        logger.error(f"Source directory does not exist: {config.source_directory}")
        sys.exit(1)

    if config.pre_sync_space_check:
        logger.info("Performing pre-sync disk space check...")
        space_check_generator = discover_files(config.source_directory, config.include_extensions)
        perform_space_check(space_check_generator, config)

    files_processed = 0
    files_copied = 0

    # Discover files
    files_to_sync = discover_files(config.source_directory, config.include_extensions)

    if args.dry_run:
        for source_file in files_to_sync:
            dest_file = generate_destination_path(
                source_file, 
                config.source_directory, 
                config.destination_base, 
                config.folder_format,
                config.organization_mode,
                config.date_source
            )
            logger.info(f"[DRY RUN] Would copy {source_file.name} to {dest_file.relative_to(config.destination_base.parent)}")
            files_processed += 1
        logger.info(f"Dry run complete. Would process {files_processed} files.")
    else:
        # Concurrent copying
        with ThreadPoolExecutor(max_workers=config.max_workers) as executor:
            future_to_file = {
                executor.submit(process_single_file, source_file, config): source_file 
                for source_file in files_to_sync
            }
            
            for future in as_completed(future_to_file):
                files_processed += 1
                if future.result():
                    files_copied += 1

        logger.info(f"Sync complete. Processed {files_processed} files, copied {files_copied}.")

if __name__ == "__main__":
    main()
