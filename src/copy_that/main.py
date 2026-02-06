import argparse
import logging
import sys
from pathlib import Path

from copy_that.config import load_config
from copy_that.discovery import discover_files
from copy_that.organizer import generate_destination_path
from copy_that.processor import copy_file

def main():
    parser = argparse.ArgumentParser(description="Copy and organize files from source to destination.")
    parser.add_Par_arg = parser.add_argument("--config", type=Path, default=Path("config.yaml"), help="Path to config file")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be copied without actually copying")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")
    
    args = parser.parse_args()

    # Setup logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=log_level, format="%(levelname)s: %(message)s")
    logger = logging.getLogger(__name__)

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

    files_processed = 0
    files_copied = 0

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
            if copy_file(source_file, dest_file, config.conflict_policy):
                files_copied += 1
                logger.info(f"Copied {source_file.name} -> {dest_file.relative_to(config.destination_base.parent)}")

    if args.dry_run:
        logger.info(f"Dry run complete. Would process {files_processed} files.")
    else:
        logger.info(f"Sync complete. Processed {files_processed} files, copied {files_copied}.")

if __name__ == "__main__":
    main()
