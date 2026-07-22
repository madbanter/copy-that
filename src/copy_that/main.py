from __future__ import annotations
import logging
import sys
import shutil
import time
import os
import signal
import fnmatch
import threading
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional, List, Any, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
from logging.handlers import RotatingFileHandler
from dataclasses import dataclass

import typer
from typing_extensions import Annotated
from rich.console import Console, Group
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich.align import Align
from rich.highlighter import ReprHighlighter
from rich.progress import Progress, TextColumn, BarColumn, DownloadColumn, TaskProgressColumn, TimeRemainingColumn

from copy_that.config import merge_config, Config, get_default_log_file
from copy_that.discovery import discover_files
from copy_that.organizer import generate_destination_path
from copy_that.processor import copy_file, SyncStatus, FileResult, verify_copy, get_unique_path
from copy_that.lifecycle import GracefulShutdown, ProcessLock, stop_process
from copy_that.monitor import Monitor

app = typer.Typer(help="Copy and organize files from source to destination.")
logger = logging.getLogger("copy_that")
console = Console(stderr=True)
highlighter = ReprHighlighter()

# Global reference for synchronous UI refresh
_live_ui = None
_progress = None
_overall_task_id = None

# Global references for thread-safe path registries and locks
_allocated_paths = None
_allocated_lock = None
_active_temp_files = None
_active_temp_lock = None


@dataclass
class SyncJob:
    source: Path
    destination: Path
    size: int

class SyncError(Exception):
    """Raised when a sync operation cannot be performed."""
    pass

class SyncStats:
    def __init__(self, total_expected: int = 0):
        self.total_expected = total_expected
        self.processed = 0
        self.transferred_count = 0
        self.skipped_count = 0
        self.failed_count = 0
        self.retried_count = 0
        self.total_bytes = 0

    def update(self, result: FileResult):
        self.processed += 1
        if result.status in (
            SyncStatus.COPIED,
            SyncStatus.OVERWRITTEN,
            SyncStatus.RENAMED,
        ):
            self.transferred_count += 1
        elif result.status == SyncStatus.SKIPPED:
            self.skipped_count += 1
        elif result.status == SyncStatus.FAILED:
            self.failed_count += 1

        if result.retried:
            self.retried_count += 1

        self.total_bytes += result.bytes_transferred


class AtomicGridHandler(logging.Handler):
    """Custom Handler that uses a 3-column Grid and triggers synchronous UI refreshes."""

    def __init__(self, console: Console):
        super().__init__()
        self.console = console

    def emit(self, record: logging.LogRecord) -> None:
        if record.levelno < self.level:
            return

        level_styles = {
            logging.DEBUG: "dim",
            logging.INFO: "bold cyan",
            logging.WARNING: "bold yellow",
            logging.ERROR: "bold red",
            logging.CRITICAL: "bold white on red",
        }
        level_style = level_styles.get(record.levelno, "white")

        # Determine the message to show on console
        filename = getattr(record, "filename_only", None)
        status = getattr(record, "status_text", None)
        is_dry_run = getattr(record, "is_dry_run", False)

        # Available width for the message column
        overhead = 10 + 10 + 2 + 2
        max_msg_width = self.console.width - overhead
        if max_msg_width < 10:
            max_msg_width = 10

        if filename and status:
            dry_tag = "[DRY RUN] " if is_dry_run else ""
            prefix = f"{dry_tag}{status}: "

            max_filename_len = max_msg_width - len(prefix)
            if max_filename_len < 5:
                max_filename_len = 5

            truncated_filename = truncate_middle(filename, max_filename_len)
            msg_str = f"{prefix}{truncated_filename}"
        else:
            msg_str = record.getMessage()
            if len(msg_str) > max_msg_width and max_msg_width > 20:
                msg_str = truncate_middle(msg_str, max_msg_width)

        grid = Table.grid(padding=(0, 1), expand=True)
        grid.add_column(width=12, justify="left", no_wrap=True)  # Level
        grid.add_column(justify="left", ratio=1, no_wrap=True, overflow="ellipsis")  # Message
        grid.add_column(width=10, justify="right", no_wrap=True)  # Timestamp

        level_text = Text(f"{record.levelname}", style=level_style)
        message_text = highlighter(msg_str)
        time_str = datetime.fromtimestamp(record.created).strftime("%H:%M:%S")
        time_text = Text(time_str, style="dim")

        grid.add_row(level_text, message_text, time_text)
        self.console.print(grid)




def format_bytes(size: float) -> str:
    """Format bytes into human-readable string."""
    if size == 0:
        return "0.00 B"
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024:
            return f"{size:.2f} {unit}"
        size /= 1024
    return f"{size:.2f} PB"


def generate_sync_jobs(files_to_sync: Iterable[Tuple[Path, int]], config: Config) -> List[SyncJob]:
    """
    Pre-calculate all destination paths for a list of source files.
    
    Note: While Config.source_directory is optional (to support auto-mount 
    bootstrap), sync jobs can only be generated when a specific source path 
    is active. This acts as a runtime safety barrier for downstream operations.
    """
    if not config.source_directory:
        raise ValueError("Config.source_directory must be set to generate sync jobs.")

    return [
        SyncJob(
            source_file,
            generate_destination_path(
                source_file,
                config.source_directory,
                config.destination_base,
                config.folder_format,
                config.organization_mode,
                config.date_source,
                config.filename_date_format,
                config.path_template,
            ),
            size,
        )
        for source_file, size in files_to_sync
    ]


def truncate_middle(text: str, max_length: int) -> str:
    """Truncate the middle of a string with '...' if it exceeds max_length."""
    if len(text) <= max_length:
        return text
    if max_length <= 3:
        return "..."[:max_length]

    remaining = max_length - 3
    left_len = remaining // 2
    right_len = remaining - left_len

    return f"{text[:left_len]}...{text[-right_len:] if right_len > 0 else ''}"


def print_warnings_and_errors(results: List[FileResult]):
    """Print full details of any warnings (skipped, renamed) or errors (failed)."""
    warnings = [r for r in results if r.status in (SyncStatus.SKIPPED, SyncStatus.RENAMED)]
    errors = [r for r in results if r.status == SyncStatus.FAILED]

    if warnings:
        console.print("\n[bold yellow]Warnings:[/bold yellow]")
        for r in warnings:
            console.print(f"[yellow]{r.status.value.upper()}: {r.source_path} -> {r.destination_path}[/yellow]")

    if errors:
        console.print("\n[bold red]Errors:[/bold red]")
        for r in errors:
            msg = f"[red]FAILED: {r.source_path} -> {r.destination_path}[/red]"
            if r.error_message:
                msg += f"\n  [dim]Error: {r.error_message}[/dim]"
            console.print(msg)


def print_summary(stats: SyncStats, results: List[FileResult], elapsed_time: float, dry_run: bool = False):
    """Print a detailed summary of the sync operation using Rich."""
    speed = stats.total_bytes / elapsed_time if elapsed_time > 0 else 0
    title = "Sync Summary" + (" (DRY RUN)" if dry_run else "")

    table = Table(title=title, show_header=False, box=None, padding=(0, 2))
    table.add_row("Total Files Processed:", str(stats.processed))
    table.add_row(f"{'Would copy' if dry_run else 'Copied'}:", str(stats.transferred_count), style="green")
    table.add_row(f"{'Would skip' if dry_run else 'Skipped'}:", str(stats.skipped_count), style="yellow")
    table.add_row(f"{'Would fail' if dry_run else 'Failed'}:", str(stats.failed_count), style="red")
    table.add_row("Items Retried:", str(stats.retried_count), style="cyan")

    data_label = "Data to transfer" if dry_run else "Total Data"
    table.add_row(f"{data_label}:", format_bytes(stats.total_bytes))
    table.add_row("Elapsed Time:", f"{elapsed_time:.2f} seconds")

    if not dry_run and stats.total_bytes > 0:
        table.add_row("Average Speed:", f"{format_bytes(int(speed))}/s")

    console.print(Align.center(Panel(table, expand=False, border_style="blue")))


class LiveSummaryRenderable:
    """Renderable for the live-updated summary footer."""
    def __init__(self, stats: SyncStats, start_time: float, dry_run: bool):
        self.stats = stats
        self.start_time = start_time
        self.dry_run = dry_run

    def __rich__(self) -> Table:
        elapsed = time.perf_counter() - self.start_time
        w = console.width - 4
        table = Table(box=None, padding=(0, 2), width=w if w > 0 else None)
        table.add_column("Progress", style="magenta", no_wrap=True, overflow="crop")
        table.add_column("Processed", style="cyan", no_wrap=True, overflow="crop")
        if not self.dry_run:
            table.add_column("Transferred", style="green", no_wrap=True, overflow="crop")
        table.add_column("Errors", style="red", no_wrap=True, overflow="crop")
        table.add_column("Elapsed", style="blue", no_wrap=True, overflow="crop")

        percentage = (self.stats.processed / self.stats.total_expected * 100) if self.stats.total_expected > 0 else 100
        row = [
            f"{percentage:>6.1f}%", 
            f"{self.stats.processed}/{self.stats.total_expected}{' (DRY RUN)' if self.dry_run else ''}"
        ]
        if not self.dry_run:
            row.append(f"{self.stats.transferred_count}")
        row.append(f"{self.stats.failed_count}")
        row.append(f"{elapsed:.1f}s")
        table.add_row(*row)
        return table


def perform_space_check(sync_jobs: List[SyncJob], config: Config) -> None:
    """Perform a 'Best Effort' disk space check before copying."""
    total_size_needed = sum(
        job.size for job in sync_jobs 
        if not (config.conflict_policy == "skip" and job.destination.exists())
    )
    check_path = config.destination_base
    while not check_path.exists() and check_path.parent != check_path:
        check_path = check_path.parent
    free_space = shutil.disk_usage(check_path).free
    if total_size_needed > free_space:
        mb = 1024 * 1024
        logger.warning(
            f"Possible insufficient disk space! Required: {total_size_needed / mb:.2f} MB, "
            f"Available: {free_space / mb:.2f} MB"
        )


def process_single_file(job: SyncJob, config: Config) -> FileResult:
    global _progress, _overall_task_id
    global _allocated_paths, _allocated_lock, _active_temp_files, _active_temp_lock
    task_id = None
    progress_callback = None

    if _progress is not None:
        max_filename_len = console.width - 70 if console.width else 50
        max_filename_len = max(max_filename_len, 10)
        truncated_name = truncate_middle(job.source.name, max_filename_len)
        padded_name = truncated_name.ljust(max_filename_len)

        def callback(advanced: int):
            nonlocal task_id
            if task_id is None:
                task_id = _progress.add_task("Copying", filename=padded_name, total=job.size)
            _progress.advance(task_id, advanced)
            if _overall_task_id is not None:
                _progress.advance(_overall_task_id, advanced)

        progress_callback = callback

    try:
        return copy_file(
            job.source, job.destination, config.conflict_policy, config.verification_method,
            config.verification_failure_behavior, buffer_size=config.buffer_size,
            max_retries=config.max_retries, retry_base_delay=config.retry_base_delay,
            retry_exponential_backoff=config.retry_exponential_backoff,
            progress_callback=progress_callback,
            allocated_paths=_allocated_paths,
            allocated_lock=_allocated_lock,
            active_temp_files=_active_temp_files,
            active_temp_lock=_active_temp_lock
        )
    finally:
        if _progress is not None and task_id is not None:
            _progress.remove_task(task_id)


def setup_logging(config: Config, dry_run: bool) -> None:
    """Configure logging for copy_that and root."""
    root_logger = logging.getLogger()
    # Remove existing handlers from root to prevent double-printing if we propagate
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
        
    main_logger = logging.getLogger("copy_that")
    main_logger.handlers = []
    main_logger.propagate = True  # Enable propagation for caplog and audit file

    rich_handler = AtomicGridHandler(console=console)
    level = logging.DEBUG if config.output_verbosity == "verbose" else (
        logging.ERROR if config.output_verbosity == "minimal" else logging.INFO
    )
    rich_handler.setLevel(level)
    main_logger.setLevel(level)
    main_logger.addHandler(rich_handler)

    if config.log_file and (not dry_run or config.output_verbosity == "verbose"):
        try:
            config.log_file.parent.mkdir(parents=True, exist_ok=True)
            if not os.access(config.log_file.parent, os.W_OK):
                raise PermissionError(f"Directory not writable: {config.log_file.parent}")
            file_handler = RotatingFileHandler(
                config.log_file, maxBytes=config.max_log_size, backupCount=config.log_backup_count
            )
            file_handler.setLevel(logging.DEBUG)
            file_handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
            root_logger.addHandler(file_handler)
            if root_logger.level > logging.DEBUG:
                root_logger.setLevel(logging.DEBUG)
        except Exception as e:
            logger.warning(f"Could not initialize log file: {e}")


def run_dry_run(sync_jobs: List[SyncJob], config: Config, stats: SyncStats) -> List[FileResult]:
    results = []
    for job in sync_jobs:
        source_file = job.source
        dest_file = job.destination
        status = SyncStatus.COPIED
        level = logging.INFO

        if dest_file.exists():
            level = logging.WARNING
            if config.conflict_policy == "skip":
                is_match = (
                    config.verification_method == "none" or
                    verify_copy(source_file, dest_file, config.verification_method, buffer_size=config.buffer_size)
                )
                status = SyncStatus.SKIPPED if is_match else SyncStatus.OVERWRITTEN
            elif config.conflict_policy == "overwrite":
                status = SyncStatus.OVERWRITTEN
            elif config.conflict_policy == "rename":
                dest_file = get_unique_path(dest_file)
                status = SyncStatus.RENAMED

        status_text = status.value.capitalize()
        logger.log(
            level,
            f"[DRY RUN] {status_text}: {source_file} -> {dest_file}",
            extra={"filename_only": source_file.name, "status_text": status_text, "is_dry_run": True}
        )
        result = FileResult(
            status,
            source_file,
            dest_file,
            bytes_transferred=(job.size if status != SyncStatus.SKIPPED else 0)
        )
        results.append(result)
        stats.update(result)
        # Refresh from the main thread (dry-run is synchronous) so the display
        # updates once per file rather than on every internal render cycle.
        if _live_ui is not None:
            _live_ui.refresh()
    return results


def run_sync_jobs(sync_jobs: List[SyncJob], config: Config, stats: SyncStats) -> List[FileResult]:
    results = []
    with ThreadPoolExecutor(max_workers=config.max_workers) as executor:
        future_to_job = {executor.submit(process_single_file, job, config): job for job in sync_jobs}
        for future in as_completed(future_to_job):
            result = future.result()
            status_text = result.status.value.capitalize()
            msg = f"{status_text}: {result.source_path} -> {result.destination_path}"

            if result.status == SyncStatus.COPIED:
                logger.info(msg, extra={"filename_only": result.source_path.name, "status_text": status_text})
            elif result.status == SyncStatus.FAILED:
                logger.error(
                    f"Failed: {result.source_path} - {result.error_message}",
                    extra={"filename_only": result.source_path.name, "status_text": "Failed"}
                )
            else:
                logger.warning(msg, extra={"filename_only": result.source_path.name, "status_text": status_text})

            results.append(result)
            stats.update(result)
            # Refresh from the main thread only — avoids concurrent write races.
            if _live_ui is not None:
                _live_ui.refresh()
    return results


def run_sync(config: Config, dry_run: bool = False, show_summary: bool = True) -> List[FileResult]:
    """Helper to perform a full sync operation with UI and logging."""
    if not config.source_directory:
        raise SyncError("Source directory is not specified.")
        
    if not config.source_directory.exists():
        raise SyncError(f"Source directory does not exist: {config.source_directory}")

    files_to_sync = list(discover_files(
        config.source_directory, config.include_extensions, config.exclude_patterns, config.exclude_regex
    ))
    
    if not files_to_sync:
        if config.output_verbosity != "minimal":
            logger.info("No files found matching criteria.")
        return []

    sync_jobs = generate_sync_jobs(files_to_sync, config)

    if config.pre_sync_space_check:
        logger.info("Performing pre-sync disk space check...")
        perform_space_check(sync_jobs, config)

    stats = SyncStats(total_expected=len(sync_jobs))
    start_time = time.perf_counter()
    
    from rich.live import Live
    global _live_ui, _progress, _overall_task_id
    global _allocated_paths, _allocated_lock, _active_temp_files, _active_temp_lock

    _allocated_paths = set()
    _allocated_lock = threading.Lock()
    _active_temp_files = set()
    _active_temp_lock = threading.Lock()

    # Single fixed-height progress bar: stable line count eliminates height-change flicker.
    total_bytes = sum(job.size for job in sync_jobs)
    _progress = Progress(
        TextColumn("[cyan]Syncing[/cyan]", justify="left"),
        TextColumn("{task.fields[filename]}", justify="left"),
        BarColumn(bar_width=30),
        TaskProgressColumn(),
        DownloadColumn(),
        TimeRemainingColumn(),
        console=console,
    )
    _overall_task_id = _progress.add_task("Total Progress", filename="", total=total_bytes if total_bytes > 0 else 1)
    group = Group(_progress, LiveSummaryRenderable(stats, start_time, dry_run))

    # auto_refresh at 4fps: smooth progress for large files. Height is fixed (single
    # aggregate task), so background redraws no longer cause flickering.
    _live_ui = Live(group, console=console, auto_refresh=True, refresh_per_second=4, transient=True)

    try:
        with _live_ui:
            _live_ui.refresh()  # Initial render
            if dry_run:
                results = run_dry_run(sync_jobs, config, stats)
            else:
                results = run_sync_jobs(sync_jobs, config, stats)
            _live_ui.refresh()  # Final render before exit
    finally:
        # Graceful cleanup of any remaining orphaned temporary files
        if _active_temp_files:
            with _active_temp_lock:
                for temp_path in list(_active_temp_files):
                    try:
                        temp_path.unlink(missing_ok=True)
                    except Exception:
                        pass

        _live_ui = None
        _progress = None
        _overall_task_id = None
        _allocated_paths = None
        _allocated_lock = None
        _active_temp_files = None
        _active_temp_lock = None

    end_time = time.perf_counter()
    
    if show_summary:
        print_warnings_and_errors(results)
        print_summary(stats, results, end_time - start_time, dry_run=dry_run)
        
    return results


@app.command()
def sync(
    config_path: Annotated[Optional[Path], typer.Option("--config", "-c", help="Path to config file")] = None,
    source: Annotated[Optional[Path], typer.Option("--source", "-s", help="Source directory")] = None,
    dest: Annotated[Optional[Path], typer.Option("--dest", "-d", help="Destination base directory")] = None,
    mode: Annotated[Optional[str], typer.Option("--mode", help="Organization mode (date, mirror)")] = None,
    template: Annotated[Optional[str], typer.Option("--template", help="Path template (e.g., '{year}/{filename}.{ext}')")] = None,
    format: Annotated[Optional[str], typer.Option("--format", help="Folder format for date mode")] = None,
    date_source: Annotated[Optional[str], typer.Option("--date-source", help="Date source (creation, modification, filename, exif)")] = None,
    filename_date_format: Annotated[Optional[str], typer.Option("--filename-date-format", help="Date format in filename")] = None,
    extensions: Annotated[Optional[List[str]], typer.Option("--ext", help="Include extensions")] = None,
    exclude: Annotated[Optional[List[str]], typer.Option("--exclude", help="Exclude glob patterns")] = None,
    exclude_regex: Annotated[Optional[List[str]], typer.Option("--exclude-regex", help="Exclude regex patterns")] = None,
    conflict: Annotated[Optional[str], typer.Option("--conflict", help="Conflict policy")] = None,
    verify: Annotated[Optional[str], typer.Option("--verify", help="Verification method")] = None,
    verify_behavior: Annotated[Optional[str], typer.Option("--verify-behavior", help="Verification failure behavior")] = None,
    space_check: Annotated[Optional[bool], typer.Option("--space-check/--no-space-check", help="Enable/disable space check")] = None,
    workers: Annotated[Optional[int], typer.Option("--workers", help="Max workers")] = None,
    buffer_size: Annotated[Optional[int], typer.Option("--buffer-size", help="Buffer size")] = None,
    retries: Annotated[Optional[int], typer.Option("--retries", help="Max retries")] = None,
    retry_delay: Annotated[Optional[float], typer.Option("--retry-delay", help="Retry delay")] = None,
    backoff: Annotated[Optional[bool], typer.Option("--backoff/--no-backoff", help="Exponential backoff")] = None,
    output_verbosity: Annotated[Optional[str], typer.Option("--verbosity", help="Verbosity")] = None,
    log: Annotated[bool, typer.Option("--log", help="Enable audit logging")] = False,
    log_file: Annotated[Optional[Path], typer.Option("--log-file", help="Audit log file path")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Dry run mode")] = False,
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Shortcut for verbose")] = False,
):
    """Sync and organize files from source to destination."""
    effective_log_file = log_file if log_file else (get_default_log_file() if log else None)
    cli_overrides = {
        "source_directory": source, 
        "destination_base": dest, 
        "organization_mode": mode, 
        "path_template": template,
        "folder_format": format, 
        "date_source": date_source, 
        "filename_date_format": filename_date_format,
        "include_extensions": extensions, 
        "exclude_patterns": exclude, 
        "exclude_regex": exclude_regex,
        "conflict_policy": conflict, 
        "verification_method": verify, 
        "verification_failure_behavior": verify_behavior,
        "pre_sync_space_check": space_check, 
        "max_workers": workers, 
        "buffer_size": buffer_size,
        "max_retries": retries, 
        "retry_base_delay": retry_delay, 
        "retry_exponential_backoff": backoff,
        "output_verbosity": "verbose" if verbose else output_verbosity, 
        "log_file": effective_log_file,
    }

    try:
        config = merge_config(config_path, **cli_overrides)
    except Exception as e:
        # Fallback logging if setup_logging hasn't run yet
        logging.basicConfig(level=logging.ERROR)
        logger.error(f"Configuration initialization failed: {e}")
        sys.exit(1)

    setup_logging(config, dry_run)
    
    if not config.source_directory:
        logger.error("Sync aborted: Source directory is not defined (check config or provide --source).")
        sys.exit(1)

    logger.info(f"Source: {config.source_directory}")
    logger.info(f"Destination: {config.destination_base}")
    logger.info(f"Mode: {config.organization_mode}")

    try:
        run_sync(config, dry_run=dry_run)
    except SyncError as e:
        logger.error(str(e))
        sys.exit(1)


@app.command()
def watch(
    config_path: Annotated[Optional[Path], typer.Option("--config", "-c", help="Path to config file")] = None,
    source: Annotated[Optional[Path], typer.Option("--source", "-s", help="Source directory")] = None,
    dest: Annotated[Optional[Path], typer.Option("--dest", "-d", help="Destination base directory")] = None,
    debounce: Annotated[Optional[float], typer.Option("--debounce", help="Debounce period in seconds")] = None,
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Shortcut for verbose")] = False,
):
    """Monitor source directory for changes and sync automatically."""
    cli_overrides = {
        "source_directory": source, 
        "destination_base": dest, 
        "watch_debounce": debounce, 
        "output_verbosity": "verbose" if verbose else None
    }
    try:
        config = merge_config(config_path, **cli_overrides)
    except Exception as e:
        logging.basicConfig(level=logging.ERROR)
        logger.error(f"Configuration error: {e}")
        sys.exit(1)

    setup_logging(config, False)

    if not config.source_directory:
        logger.error("Source directory is required for watch. Please provide --source or set it in config.")
        sys.exit(1)

    lock = ProcessLock("watch")
    if not lock.acquire():
        logger.error("Error: A watch process is already running (lock held).")
        sys.exit(1)

    shutdown = GracefulShutdown()

    def trigger_sync():
        try:
            run_sync(config, show_summary=False)
        except SyncError as e:
            logger.warning(f"Watch sync failed: {e}")

    try:
        with Monitor(shutdown) as monitor:
            monitor.watch_files(config.source_directory, trigger_sync, debounce=config.watch_debounce)
            monitor.run()
    finally:
        lock.release()


@app.command()
def auto_mount(
    config_path: Annotated[Optional[Path], typer.Option("--config", "-c", help="Path to config file")] = None,
    dest: Annotated[Optional[Path], typer.Option("--dest", "-d", help="Destination base directory")] = None,
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Shortcut for verbose")] = False,
):
    """Monitor for new drive mounts and sync them automatically."""
    cli_overrides = {
        "destination_base": dest, 
        "auto_mount_enabled": True, 
        "output_verbosity": "verbose" if verbose else None
    }
    try:
        config = merge_config(config_path, **cli_overrides)
    except Exception as e:
        logging.basicConfig(level=logging.ERROR)
        logger.error(f"Configuration error: {e}")
        sys.exit(1)

    setup_logging(config, False)

    lock = ProcessLock("auto-mount")
    if not lock.acquire():
        logger.error("Error: An auto-mount process is already running (lock held).")
        sys.exit(1)

    shutdown = GracefulShutdown()

    def on_mount(mount_path: Path):
        # Whitelist check
        is_whitelisted = False
        if config.auto_mount_whitelist:
            for pattern in config.auto_mount_whitelist:
                if fnmatch.fnmatch(mount_path.name, pattern):
                    is_whitelisted = True
                    break
        
        should_sync = is_whitelisted
        if not is_whitelisted and config.auto_mount_interactive_prompt and sys.stdin.isatty():
            if typer.confirm(f"Unknown drive '{mount_path.name}' detected. Sync from this source?"):
                should_sync = True
        
        if should_sync:
            # Create a localized config for this mount
            mount_config = config.model_copy(update={"source_directory": mount_path})
            try:
                run_sync(mount_config, show_summary=True)
            except SyncError as e:
                logger.warning(f"Auto-mount sync failed for {mount_path}: {e}")

    try:
        with Monitor(shutdown) as monitor:
            monitor.watch_mounts(config.auto_mount_points, on_mount, config.auto_mount_whitelist)
            monitor.run()
    finally:
        lock.release()


@app.command()
def stop(
    watch: Annotated[bool, typer.Option("--watch", help="Stop watch process")] = False,
    auto_mount: Annotated[bool, typer.Option("--auto-mount", help="Stop auto-mount process")] = False,
):
    """Stop active background monitoring processes. Stops all by default."""
    
    # Map flags to process names
    all_targets = {"watch": watch, "auto-mount": auto_mount}
    
    # If no flags are set, we want to stop all targets
    if not any(all_targets.values()):
        targets_to_stop = all_targets.keys()
    else:
        targets_to_stop = [name for name, active in all_targets.items() if active]
        
    stopped_anything = False
    for target in targets_to_stop:
        if stop_process(target):
            logger.info(f"Stopped {target} process.")
            stopped_anything = True
            
    if not stopped_anything:
        logger.info("No active background processes to stop.")


def main():
    # Signal handling is managed within commands via GracefulShutdown
    # but we keep a basic handler for the main entry point as a fallback.
    def signal_handler(sig, frame):
        # Reset terminal scroll region and show cursor
        sys.stdout.write("\033[r\033[?25h")
        sys.stdout.flush()
        sys.exit(0)
        
    signal.signal(signal.SIGINT, signal_handler)
    app()


if __name__ == "__main__":
    main()
