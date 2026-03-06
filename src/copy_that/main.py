import argparse
import logging
import sys
import shutil
from pathlib import Path
from typing import Iterable

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
            config.destination_base,
            config.folder_format
        )
        
        # In 'skip' mode, we only count files that don't exist yet.
        if config.conflict_policy == "skip" and dest_file.exists():
            continue
            
        total_size_needed += source_file.stat().st_size

    # Ensure destination parent exists to check disk usage
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

    if not config.source_directory.exists():
        logger.error(f"Source directory does not exist: {config.source_directory}")
        sys.exit(1)

    # If space check is enabled, we perform a pre-scan (second scan)
    if config.pre_sync_space_check:
        logger.info("Performing pre-sync disk space check...")
        space_check_generator = discover_files(config.source_directory, config.include_extensions)
        perform_space_check(space_check_generator, config)

    files_processed = 0
    files_copied = 0

    # The actual sync uses the generator directly for efficiency
    for source_file in discover_files(config.source_directory, config.include_extensions):
        dest_file = generate_destination_path(
            source_file,
            config.destination_base,
            config.folder_format
        )

        files_processed += 1

        if args.dry_run:
            logger.info(f"[DRY RUN] Would copy {source_file.name} to {dest_file.relative_to(config.destination_base.parent)}")
        else:
            if copy_file(
                source_file, 
                dest_file, 
                config.conflict_policy, 
                config.verification_method,
                config.verification_failure_behavior
            ):
                files_copied += 1
                logger.info(f"Copied {source_file.name} -> {dest_file.relative_to(config.destination_base.parent)}")

    if args.dry_run:
        logger.info(f"Dry run complete. Would process {files_processed} files.")
    else:
        logger.info(f"Sync complete. Processed {files_processed} files, copied {files_copied}.")

if __name__ == "__main__":
    main()
