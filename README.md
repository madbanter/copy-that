# CopyThat

A configurable Python utility designed to automate the transfer and organization of files from external drives (e.g., SD cards, external HDDs) to a structured destination directory.

## Core Workflow
The default workflow is optimized for photographers and media creators:
1. **Scan**: Identify media files on a source drive.
2. **Organize**: Determine the destination subfolder based on the file's creation date (`YYYYMMDD`).
3. **Copy**: Transfer new files to the destination while preserving original filenames and all metadata.

## Features
- **Preserve Metadata**: Uses `shutil.copy2` to ensure file timestamps and permissions are maintained.
- **Skip Existing**: By default, identifies files already present in the destination and skips them to avoid redundant operations.
- **Flexible Organization**: Configurable subfolder naming (defaulting to date-based structures).
- **YAML Configuration**: Easy-to-edit settings for source/destination paths and file filters.

## Configuration
The application uses a `config.yaml` file to define behavior:

```yaml
source_directory: "/Volumes/SD_CARD"
destination_base: "/Users/user/Pictures/Imports"
folder_format: "%Y%m%d"  # Result: 20231027/
include_extensions:
  - .jpg
  - .cr3
  - .mp4
  - .xmp
conflict_policy: "skip" # Options: skip, overwrite, rename
```

## Security & Principles
- **Data Integrity**: Focuses on copying rather than moving to ensure source data remains untouched.
- **Security**: No hardcoded paths, secrets, or sensitive identifiers.
- **Minimal Dependencies**: Built with standard Python libraries where possible for maximum portability.
