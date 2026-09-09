# CopyThat

A high-performance utility designed to automate the transfer and organization of files from external drives (e.g., SD cards, external HDDs) to a structured destination.

## Core Workflow

Optimized for photographers and media creators:

1. **Scan**: Identify media files on a source drive.
2. **Organize**: Generate destination paths based on date or source structure.
3. **Copy**: High-speed transfer with metadata preservation and optional verification.

## Key Features

### Smart Organization

- **Date Mode**: Automatically groups files into subfolders based on creation, modification, or dates extracted from filenames (e.g., `2024/03-March/20`).
- **Mirror Mode**: Preserves your existing folder structure exactly as it is on the source.
- **Case-Insensitive Filtering**: Broad support for extensions (e.g., `.JPG` and `.jpg` are handled identically).

### Reliability & Safety

- **Atomic Writes**: Every copy operation is performed to a temporary `.ct-tmp` file and only renamed to the final path after a successful integrity check. This prevents half-finished or corrupted files from cluttering your destination.
- **Interrupt Cleanup**: If the process is interrupted mid-sync, any in-flight `.ct-tmp` files are automatically unlinked before exit, leaving no partial data at the destination.
- **Robust Retries**: Automatically handles transient hardware glitches or driver "hiccups" with configurable retries and exponential backoff.
- **Metadata Preservation**: Keeps your original file timestamps and permissions intact, with a graceful fallback for filesystems with limited attribute support (e.g., FAT32, exFAT, SMB shares).
- **Data Verification**: Optional post-copy verification (based on file size or checksums ) to ensure data integrity.
- **Safe Conflicts**: Configurable policies to skip, overwrite, or rename files if they already exist at the destination. Rename allocation is thread-safe, preventing two workers from targeting the same suffix concurrently.
- **Pre-flight Checks**: Optional disk space estimation and a comprehensive **Dry Run** mode to see results before any data is moved.

### Modern CLI Experience

- **Clean Feedback**: Concise console logging with automated filename truncation and sequential output to maintain a clear history.
- **Rich Reporting**: Real-time progress bars for active transfers and a live summary footer that automatically cleans itself up (transient display) to leave a pristine post-sync detailed report.
- **Unified Logging**: Consistent logging across dry runs and actual executions, with full path details available in audit logs.
- **Verbosity Control**: Three levels of verbosity (minimal, normal, verbose) to keep the console clean or provide deep technical context.
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

## Shell Completions

To install shell completions for your current shell:

```bash
copy-that --install-completion
```

## Background Services

CopyThat runs background services for file watching and mount detection.

- **Locking:** These services use cross-platform file-based locking (via `filelock`) to ensure single-instance operation. If a service crashes, the OS automatically releases the lock, eliminating "stale PID" issues.
- **Stopping:** Run `copy-that stop` to terminate all active background services. You can also target specific services using `--watch` or `--auto-mount`. Services are designed to shut down gracefully upon receiving a `SIGTERM` signal. _(Note: On Windows, background services are terminated forcefully due to OS limitations with signal handling, but file locks are still automatically released by the OS.)_

## CLI Options

- `--config`, `-c`: Path to the YAML configuration file.
- `--source`, `-s`: Source directory to scan for files.
- `--dest`, `-d`: Destination base directory for organization.
- `--mode`: Organization mode (`date` or `mirror`). (Default: `date`)
- `--template`: Path template (e.g., '{year}/{make}/{filename}.{ext}'). Overrides `mode` and `folder-format`.
- `--format`: Folder format string for `date` mode. (Default: `%Y%m%d`)
- `--date-source`: Source for date metadata (`creation`, `modification`, `filename`, or `exif`). (Default: `creation`)
- `--filename-date-format`: Date format pattern (strftime) if `date-source` is set to `filename`. The date is extracted by regex from anywhere in the filename stem, so a prefix or suffix (e.g., `DSC_`, `_edited`) is handled automatically.
- `--ext`: Include specific file extensions (can be repeated).
- `--exclude`: Glob pattern(s) to exclude (can be repeated). Patterns are matched against both the bare filename and the path relative to the source directory, so subdirectory globs such as `RAW/**` work as expected.
- `--exclude-regex`: Regex pattern(s) to exclude (can be repeated). Applied against both the bare filename and the relative path from the source root.
- `--conflict`: Conflict policy (`skip`, `overwrite`, or `rename`).
- `--verify`: Verification method (`none`, `size`, `md5`, or `sha1`).
- `--verify-behavior`: Verification failure behavior (`retry`, `ignore`, or `delete`).
- `--space-check` / `--no-space-check`: Enable/disable pre-sync disk space check.
- `--workers`: Maximum number of concurrent workers.
- `--buffer-size`: Buffer size in bytes for copy/hashing operations.
- `--retries`: Max retries for transient errors.
- `--retry-delay`: Base delay for retries (seconds).
- `--backoff` / `--no-backoff`: Enable/disable exponential backoff.
- `--dry-run`: Simulation mode.
- `--verbose`, `-v`: Enable detailed logging.

## Configuration

CopyThat looks for settings in:

1. `./config.yaml`
2. `~/.config/copy-that/config.yaml`
3. `~/.copy-that.yaml`

Relative paths within these files (e.g., `source_directory: ./photos`) are resolved relative to the **config file's location**, ensuring your setup works from any directory.

See `example_config.yaml` for a full list of supported settings and descriptions.

## Development

This project uses `uv` for dependency management.

```bash
# Install all dependencies (including dev tools)
uv sync --group dev

# Run tests with coverage
uv run pytest --cov=copy_that --cov-report=term-missing

# Lint and format code
uv run ruff check src/ tests/
uv run ruff format src/ tests/

# Build standalone CLI executable
uv run pyinstaller copy_that_cli.spec

# Build tray app
uv run pyinstaller copy_that_tray.spec
```

## Technical Principles

- **Concurrent I/O**: Uses multi-threading to maximize throughput across different storage types. Destination paths are reserved atomically alongside collision resolution inside scoped thread locks (`allocated_lock`), preventing worker threads from racing on identical output paths or temporary `.ct-tmp` files.
- **Data-First**: Always copies rather than moves, ensuring your source media remains untouched.
- **Strict Validation**: Utilizes type-safe configuration parsing to catch errors early.
- **Robust Error Handling**: Gracefully handles disk disconnection, permission issues, and corrupt files. Unfinished temporary files are cleaned up automatically on interrupt or error.
- **Multi-Mount Watching**: When using auto-mount detection, all configured `auto_mount_points` are monitored simultaneously.
