# CopyThat TODO List

## 1. User Experience & Feedback

- [ ] **Progress Bars**: Implement visual progress bars (e.g., using `tqdm` or `rich`) for large file transfers.
- [ ] **Summary Report**: Add a detailed summary after completion including total data transferred, elapsed time, average speed, and any errors.
- [ ] **Enhanced Dry Run**: Improve dry-run output to explicitly show skipped files and potential disk space issues.

## 2. Performance

- [x] **Optimized Discovery**: Consider using `os.scandir` instead of `pathlib.Path.rglob("*")` for faster discovery in large directory trees.
- [x] **Modern Checksumming**: Utilize `hashlib.file_digest` (Python 3.11+) for more efficient checksum calculations during verification.
- [x] **Buffered I/O**: Explore custom buffer sizes with `shutil.copyfileobj` to optimize performance across different storage types.

## 3. Functionality & Features

- [ ] **Exif-based Organization**: Integrate an Exif library to use "Date Taken" metadata for more accurate media organization.
- [ ] **Advanced Filtering**: Support glob patterns, regex, or exclusion lists (e.g., ignoring `.DS_Store` or `__pycache__`).
- [ ] **Template-based Organization**: Move to a flexible template system (e.g., `{year}/{camera_model}/{extension}/{filename}`).
- [ ] **Atomic Writes**: Copy files to a temporary `.tmp` extension first and rename them only after successful verification.

## 4. Reliability & Maintainability

- [ ] **Robust Retries**: Enhance retry logic with exponential backoff for handling intermittent drive connectivity issues.
- [ ] **Persistent Logging**: Add an option to save logs to a file in the destination directory for auditing and troubleshooting.
- [x] **Extended Testing**: Expand the test suite to include more edge cases and simulated failure scenarios. (Completed: Increased coverage to 97%)

## 5. CLI & Configuration

- [x] **Full CLI Support**: Allow overriding all configuration options via command-line arguments. (Completed using Typer)
- [x] **Configuration Search**: Automatically search for configuration files in standard locations (e.g., `~/.config/copy-that/config.yaml`).
- [x] **Shell Completions**: Generate shell completion scripts for `bash`, `zsh`, and `fish`.

## 6. Automation & Monitoring

- [ ] **Auto-Copy on Mount**: Detect when external media (SD cards, CF cards, etc.) are mounted and automatically trigger a sync.
- [ ] **Watch Mode**: Implement a continuous "watch" mode that monitors specified directories for new files and processes them in real-time.
- [ ] **Background Service**: Support running the app as a background daemon or system service.

## 7. Deployment & Future Enhancements

- [ ] **Standalone Application**: Package the app as a standalone executable.
- [ ] **Menu Bar / System Tray Icon**: Add a resident icon for quick access and status monitoring.
- [ ] **Containerization**: Provide a `Dockerfile` for easier deployment.
- [ ] **Task Automation**: Use `Taskfile` or similar to automate common workflows like `test`, `lint`, and `dry-run`.
