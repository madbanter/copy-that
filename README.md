# CopyThat

A high-performance, configurable Python utility designed to automate the transfer and organization of files from external drives (e.g., SD cards, external HDDs) to a structured destination directory.

## Core Workflow
The default workflow is optimized for photographers and media creators:
1. **Scan**: Identify media files on a source drive.
2. **Organize**: Determine the destination path based on the chosen mode.
3. **Copy**: Transfer files to the destination while preserving original filenames and all metadata.

## Features
- **Flexible CLI**: Run with a config file, command-line overrides, or both.
- **Flexible Organization Modes**: 
  - **Date Mode**: Groups files into subfolders based on creation or modification dates.
  - **Mirror Mode**: Preserves the original folder structure of the source directory.
- **High Performance**: Concurrent file copying using `ThreadPoolExecutor` (multi-threaded).
- **Metadata Preservation**: Uses `shutil.copy2` to ensure file timestamps and permissions are maintained.
- **Data Integrity**: Optional post-copy verification (Size, MD5, or SHA1 checksums).
- **Intelligent Conflict Handling**: Configurable policies to skip, overwrite, or rename files when they exist at the destination.
- **Case-Insensitive Matching**: Automatically matches file extensions regardless of case (e.g., `.JPG` matches `.jpg`).
- **Safety Checks**: Optional pre-sync disk space check to ensure the destination has enough room.
- **Fail-Safe Behavior**: Configurable responses to verification failures (retry, ignore, or delete).
- **YAML Configuration**: Easy-to-edit settings for persistent workflows.

## Usage
Run the application using `uv`:

```bash
# Basic run using config.yaml defaults
uv run copy-that

# Run with a specific configuration file
uv run copy-that --config my-custom-config.yaml

# Override source and destination via CLI
uv run copy-that --source /Volumes/SD_CARD --dest ~/Pictures/Imports

# Combine config file with CLI overrides
uv run copy-that --config defaults.yaml --mode mirror --dry-run
```

### CLI Options
- `--config`, `-c`: Path to the YAML configuration file (default: `config.yaml`).
- `--source`, `-s`: Source directory to scan for files.
- `--dest`, `-d`: Destination base directory for organization.
- `--mode`: Organization mode (`date` or `mirror`).
- `--format`: Folder format string for `date` mode (e.g., `%Y/%m/%d`).
- `--date-source`: Source for date metadata (`creation` or `modification`).
- `--ext`: Include specific file extensions (can be repeated, e.g., `--ext .jpg --ext .arw`).
- `--conflict`: Conflict policy (`skip`, `overwrite`, or `rename`).
- `--verify`: Verification method (`none`, `size`, `md5`, or `sha1`).
- `--verify-behavior`: Behavior on verification failure (`retry`, `ignore`, or `delete`).
- `--space-check` / `--no-space-check`: Enable/disable pre-sync disk space check.
- `--workers`: Maximum number of concurrent workers (threads).
- `--buffer-size`: Buffer size in bytes for copying and hashing (default: 1,048,576 bytes / 1MB).
- `--dry-run`: Show what would be copied without actually performing any operations.
- `--verbose`, `-v`: Enable detailed logging (DEBUG level).

## Configuration
The application uses a `config.yaml` file to define persistent settings. CLI arguments always take precedence over values in the configuration file.

```yaml
# Source & Destination
source_directory: "~/Pictures/Source"
destination_base: "~/Pictures/Organized"

# Organization
organization_mode: "date"  # options: date, mirror
folder_format: "%Y/%m-%B/%d"  # used only in 'date' mode
date_source: "creation"    # options: creation, modification (used only in 'date' mode)

# File Filters
include_extensions:
  - .jpg
  - .cr3
  - .mp4
  - .xmp

# Copy Behavior
conflict_policy: "skip" # options: skip, overwrite, rename
max_workers: null       # number of threads (null = system default, 1 = sequential)
buffer_size: 1048576    # 1MB buffer size (can be tuned for performance)

# Verification & Safety
verification_method: "none" # options: none, size, md5, sha1
verification_failure_behavior: "retry" # options: retry, ignore, delete
pre_sync_space_check: false # if true, performs a pre-scan to estimate required space
```

## Security & Principles
- **Data Integrity**: Focuses on copying rather than moving to ensure source data remains untouched.
- **Efficiency**: Uses generators for file discovery and concurrency for high-speed transfers.
- **Pydantic Validation**: Configuration is strictly validated at startup to prevent runtime errors.
