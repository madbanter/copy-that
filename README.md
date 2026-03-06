# CopyThat

A high-performance, configurable Python utility designed to automate the transfer and organization of files from external drives (e.g., SD cards, external HDDs) to a structured destination directory.

## Core Workflow
The default workflow is optimized for photographers and media creators:
1. **Scan**: Identify media files on a source drive.
2. **Organize**: Determine the destination path based on the chosen mode.
3. **Copy**: Transfer files to the destination while preserving original filenames and all metadata.

## Features
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
- **YAML Configuration**: Easy-to-edit settings for source/destination paths and file filters.

## Usage
Run the script using Python:

```bash
uv run python -m copy_that.main --config config.yaml
```

### CLI Arguments
- `--config`: Path to the YAML configuration file (default: `config.yaml`).
- `--dry-run`: Show what would be copied without actually performing any operations.
- `--verbose`: Enable detailed logging (DEBUG level).

## Configuration
The application uses a `config.yaml` file to define behavior:

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

# Verification & Safety
verification_method: "none" # options: none, size, md5, sha1
verification_failure_behavior: "retry" # options: retry, ignore, delete
pre_sync_space_check: false # if true, performs a pre-scan to estimate required space
```

## Security & Principles
- **Data Integrity**: Focuses on copying rather than moving to ensure source data remains untouched.
- **Efficiency**: Uses generators for file discovery to maintain a low memory footprint.
- **Zero Dependencies**: Uses standard library features (`shutil.copy2`, `hashlib`, `concurrent.futures`) for core logic.
- **Pydantic Validation**: Configuration is strictly validated at startup to prevent runtime errors.
