# CopyThat

A high-performance utility designed to automate the transfer and organization of files from external drives (e.g., SD cards, external HDDs) to a structured destination.

## Core Workflow
Optimized for photographers and media creators:
1. **Scan**: Identify media files on a source drive.
2. **Organize**: Generate destination paths based on date or source structure.
3. **Copy**: High-speed transfer with metadata preservation and optional verification.

## Key Features

### Smart Organization
- **Date Mode**: Automatically groups files into subfolders based on creation, modification, or **dates extracted from filenames** (e.g., `2024/03-March/20`).
- **Mirror Mode**: Preserves your existing folder structure exactly as it is on the source.
- **Case-Insensitive Filtering**: Broad support for extensions (e.g., `.JPG` and `.jpg` are handled identically).

### Reliability & Safety
- **Metadata Preservation**: Keeps your original file timestamps and permissions intact.
- **Data Verification**: Optional post-copy checksumming (MD5, SHA1, or Size) to ensure data integrity.
- **Safe Conflicts**: Configurable policies to skip, overwrite, or rename files if they already exist at the destination.
- **Pre-flight Checks**: Optional disk space estimation and a comprehensive **Dry Run** mode to see results before any data is moved.

### Modern CLI Experience
- **Zero-Config Discovery**: Automatically searches for configuration in standard locations (`./config.yaml`, `~/.config/copy-that/`, etc.).
- **Interactive Completions**: Full tab-completion support for `bash`, `zsh`, and `fish`.
- **Global Accessibility**: Install once and run `copy-that` from any directory.

## Installation

```bash
# Install globally from the project directory (Editable mode)
uv tool install --editable .

# Ensure your PATH is updated (follow on-screen instructions or restart terminal)
uv tool update-shell
```

## Usage

```bash
# Basic run from any directory (uses automatic configuration search)
copy-that

# Use the current directory as source
copy-that --source . --dest ~/Pictures/Imports --dry-run

# Override organization mode
copy-that --mode mirror
```

### Shell Completions
To install shell completions for your current shell:
```bash
copy-that --install-completion
```

### CLI Options
- `--config`, `-c`: Path to the YAML configuration file. If not provided, it searches standard locations.
- `--source`, `-s`: Source directory to scan for files. Supports `.` for the current directory.
- `--dest`, `-d`: Destination base directory for organization.
- `--mode`: Organization mode (`date` or `mirror`).
- `--format`: Folder format string for `date` mode (e.g., `%Y/%m/%d`).
- `--date-source`: Source for date metadata (`creation`, `modification`, or `filename`).
- `--filename-date-format`: Date format pattern if `date-source` is set to `filename` (default: `%Y-%m-%d %H.%M.%S`).
- `--ext`: Include specific file extensions (can be repeated, e.g., `--ext .jpg --ext .arw`).
- `--conflict`: Conflict policy (`skip`, `overwrite`, or `rename`).
- `--verify`: Verification method (`none`, `size`, `md5`, or `sha1`).
- `--verify-behavior`: Behavior on verification failure (`retry`, `ignore`, or `delete`).
- `--space-check` / `--no-space-check`: Enable/disable pre-sync disk space check.
- `--workers`: Maximum number of concurrent workers (threads).
- `--buffer-size`: Buffer size in bytes for copying and hashing (default: 1MB).
- `--dry-run`: Show what would be copied without actually performing any operations.
- `--verbose`, `-v`: Enable detailed logging (DEBUG level).

## Configuration
CopyThat looks for settings in:
1. `./config.yaml`
2. `~/.config/copy-that/config.yaml`
3. `~/.copy-that.yaml`

Relative paths within these files (e.g., `source_directory: ./photos`) are resolved relative to the **config file's location**, ensuring your setup works from any directory.

See `example_config.yaml` for a full list of supported settings and descriptions.

## Technical Principles
- **Concurrent I/O**: Uses multi-threading to maximize throughput across different storage types.
- **Data-First**: Always copies rather than moves, ensuring your source media remains untouched.
- **Strict Validation**: Utilizes type-safe configuration parsing to catch errors early.
- **Robust Error Handling**: Gracefully handles disk disconnection, permission issues, and corrupt files.
