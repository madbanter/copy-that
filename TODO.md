# CopyThat TODO List

## 1. User Experience & Feedback

- [ ] **Progress Bars**: Implement visual progress bars (e.g., using `rich`) for large file transfers. (Progress percentages added to live footer)
- [x] **Summary Report**: Add a detailed summary after completion including total data transferred, elapsed time, average speed, and any errors. (Completed: Box is now centered in terminal)
- [x] **Enhanced Dry Run**: Improve dry-run output to explicitly show skipped files and use pre-cached sizes. (Space check enabled by default)

## 2. Performance

- [x] **Optimized Discovery**: Uses `os.scandir` to yield sizes alongside paths, eliminating redundant `stat()` calls.
- [x] **Modern Checksumming**: Utilize `hashlib.file_digest` (Python 3.11+) for more efficient checksum calculations during verification.
- [x] **Buffered I/O**: Explore custom buffer sizes with `shutil.copyfileobj` to optimize performance across different storage types.

## 3. Functionality & Features

- [x] **Exif-based Organization**: Integrate an Exif library to use "Date Taken" metadata for more accurate media organization. (Completed using ExifRead)
- [x] **Advanced Filtering**: Support glob patterns, regex, or exclusion lists (e.g., ignoring `.DS_Store` or `__pycache__`). (Completed with glob and regex support)
- [x] **Template-based Organization**: Move to a flexible template system (e.g., `{year}/{camera_model}/{extension}/{filename}`). (Completed using token-based rendering)
- [x] **Atomic Writes**: Copy files to a temporary `.ct-tmp` extension first and rename them only after successful verification.

## 4. Reliability & Maintainability

- [x] **Robust Retries**: Enhance retry logic with exponential backoff for handling intermittent drive connectivity issues.
- [x] **Persistent Logging**: Add an option to save logs to a file in the destination directory for auditing and troubleshooting.
- [x] **Extended Testing**: Expand the test suite to include more edge cases and simulated failure scenarios. (Completed: Increased coverage to 99%)

## 5. CLI & Configuration

- [x] **Full CLI Support**: Allow overriding all configuration options via command-line arguments. (Completed using Typer)
- [x] **Configuration Search**: Automatically search for configuration files in standard locations (e.g., `~/.config/copy-that/config.yaml`).
- [x] **Shell Completions**: Generate shell completion scripts for `bash`, `zsh`, and `fish`.

## 6. Automation & Monitoring

- [x] **Auto-Copy on Mount**: Detect when external media (SD cards, CF cards, etc.) are mounted and automatically trigger a sync. (Completed)
- [x] **Watch Mode**: Implement a continuous "watch" mode that monitors specified directories for new files and processes them in real-time. (Completed)
- [x] **Background Service**: Support running the app as a background daemon or system service. (Completed via lifecycle PID management)

## 7. Deployment & Future Enhancements

- [ ] **Standalone Application**: Package the app as a standalone executable.
- [ ] **Menu Bar / System Tray Icon**: Add a resident icon for quick access and status monitoring.
- [ ] **Containerization**: Provide a `Dockerfile` for easier deployment.
- [ ] **Task Automation**: Use `Taskfile` or similar to automate common workflows like `test`, `lint`, and `dry-run`.
- [ ] **Filesystem Limitations**: Background services (watch/auto-mount) are currently limited to local filesystems due to advisory locking limitations on NFS/SMB and cloud storage. Investigate cross-platform lock-file workarounds for these environments.
