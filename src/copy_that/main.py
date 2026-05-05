from __future__ import annotations
import logging
import sys
import shutil
import time
import os
import signal
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional, List, Any
from concurrent.futures import ThreadPoolExecutor, as_completed
from logging.handlers import RotatingFileHandler

import typer
from typing_extensions import Annotated
from rich.console import Console
from rich.logging import RichHandler
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich.highlighter import ReprHighlighter

from copy_that.config import merge_config, Config, get_default_log_file
from copy_that.discovery import discover_files
from copy_that.organizer import generate_destination_path
from copy_that.processor import copy_file, SyncStatus, FileResult

app = typer.Typer(help="Copy and organize files from source to destination.")
logger = logging.getLogger("copy_that")
console = Console(stderr=True)
highlighter = ReprHighlighter()

# Global reference for synchronous UI refresh
_live_ui = None
_last_ui_update = 0

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
        if result.status in (SyncStatus.COPIED, SyncStatus.OVERWRITTEN, SyncStatus.RENAMED):
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
            logging.CRITICAL: "bold white on red"
        }
        level_style = level_styles.get(record.levelno, "white")
        
        # Determine the message to show on console
        filename = getattr(record, "filename_only", None)
        status = getattr(record, "status_text", None)
        is_dry_run = getattr(record, "is_dry_run", False)
        
        # Available width for the message column
        # Level column: 10, Time column: 10, Padding: 2*1, Buffer: 2
        overhead = 10 + 10 + 2 + 2
        max_msg_width = self.console.width - overhead
        if max_msg_width < 10: max_msg_width = 10
        
        if filename and status:
            dry_tag = "[DRY RUN] " if is_dry_run else ""
            prefix = f"{dry_tag}{status}: "
            
            # Truncate filename to fit remaining space
            max_filename_len = max_msg_width - len(prefix)
            if max_filename_len < 5: max_filename_len = 5
            
            truncated_filename = truncate_middle(filename, max_filename_len)
            msg_str = f"{prefix}{truncated_filename}"
        else:
            msg_str = record.getMessage()
            # ONLY truncate if it's a file action status or if it's exceptionally long
            if len(msg_str) > max_msg_width and max_msg_width > 20:
                msg_str = truncate_middle(msg_str, max_msg_width)

        # Create a 3-column grid for perfect alignment. 
        # expand=True + ratio=1 on the message column ensures it takes all available space
        # and stays left-aligned, pinning the timestamp to the far right.
        grid = Table.grid(padding=(0, 1), expand=True)
        grid.add_column(width=12, justify="left", no_wrap=True) # Level
        grid.add_column(justify="left", ratio=1, no_wrap=True, overflow="ellipsis") # Message
        grid.add_column(width=10, justify="right", no_wrap=True) # Timestamp

        level_text = Text(f"{record.levelname}", style=level_style)
        message_text = highlighter(msg_str)
        time_str = datetime.fromtimestamp(record.created).strftime("%H:%M:%S")
        time_text = Text(time_str, style="dim")
        
        grid.add_row(level_text, message_text, time_text)
        
        self.console.print(grid)
        
        # Throttled Synchronous Refresh
        global _last_ui_update
        now = time.perf_counter()
        if _live_ui and (now - _last_ui_update) > 0.1:
            _live_ui.refresh()
            _last_ui_update = now

def format_bytes(size: int) -> str:
    """Format bytes into human-readable string."""
    if size == 0:
        return "0.00 B"
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024:
            return f"{size:.2f} {unit}"
        size /= 1024
    return f"{size:.2f} PB"

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

    title = "Sync Summary"
    if dry_run:
        title += " (DRY RUN)"

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

    console.print("\n")
    console.print(Panel(table, expand=False, border_style="blue"))

    failed = [r for r in results if r.status == SyncStatus.FAILED]
    if failed:
        console.print("\n[bold red]Failures:[/bold red]")
        for r in failed:
            console.print(f"  - [red]{r.source_path.name}[/red]: {r.error_message}")
        console.print("-" * 40)

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

def perform_space_check(source_files: Iterable[Path], config: Config) -> None:
    """Perform a 'Best Effort' disk space check before copying."""
    total_size_needed = 0
    for source_file in source_files:
        dest_file = generate_destination_path(source_file, config.source_directory, config.destination_base, config.folder_format, config.organization_mode, config.date_source, config.filename_date_format)
        if config.conflict_policy == "skip" and dest_file.exists(): continue
        total_size_needed += source_file.stat().st_size
    check_path = config.destination_base
    while not check_path.exists() and check_path.parent != check_path: check_path = check_path.parent
    free_space = shutil.disk_usage(check_path).free
    if total_size_needed > free_space:
        mb = 1024 * 1024
        msg = f"Possible insufficient disk space! Required: {total_size_needed / mb:.2f} MB, Available: {free_space / mb:.2f} MB"
        logger.warning(msg)

def process_single_file(source_file: Path, config: Config) -> FileResult:
    dest_file = generate_destination_path(source_file, config.source_directory, config.destination_base, config.folder_format, config.organization_mode, config.date_source, config.filename_date_format)
    return copy_file(source_file, dest_file, config.conflict_policy, config.verification_method, config.verification_failure_behavior, buffer_size=config.buffer_size)

@app.command()
def sync(
    config_path: Annotated[Optional[Path], typer.Option("--config", "-c", help="Path to config file")] = None,
    source: Annotated[Optional[Path], typer.Option("--source", "-s", help="Source directory")] = None,
    dest: Annotated[Optional[Path], typer.Option("--dest", "-d", help="Destination base directory")] = None,
    mode: Annotated[Optional[str], typer.Option("--mode", help="Organization mode (date, mirror)")] = None,
    format: Annotated[Optional[str], typer.Option("--format", help="Folder format for date mode")] = None,
    date_source: Annotated[Optional[str], typer.Option("--date-source", help="Date source (creation, modification, filename)")] = None,
    filename_date_format: Annotated[Optional[str], typer.Option("--filename-date-format", help="Date format in filename (for_date-source=filename)")] = None,
    extensions: Annotated[Optional[List[str]], typer.Option("--ext", help="Include extensions (can be repeated)")] = None,
    conflict: Annotated[Optional[str], typer.Option("--conflict", help="Conflict policy (skip, overwrite, rename)")] = None,
    verify: Annotated[Optional[str], typer.Option("--verify", help="Verification method (none, size, md5, sha1)")] = None,
    verify_behavior: Annotated[Optional[str], typer.Option("--verify-behavior", help="Verification failure behavior (retry, ignore, delete)")] = None,
    space_check: Annotated[Optional[bool], typer.Option("--space-check/--no-space-check", help="Enable/disable pre-sync space check")] = None,
    workers: Annotated[Optional[int], typer.Option("--workers", help="Max workers for concurrent copying")] = None,
    buffer_size: Annotated[Optional[int], typer.Option("--buffer-size", help="Buffer size in bytes for copying and hashing")] = None,
    output_verbosity: Annotated[Optional[str], typer.Option("--verbosity", help="Output verbosity (minimal, normal, verbose)")] = None,
    log: Annotated[bool, typer.Option("--log", help="Enable audit logging to standard platform path")] = False,
    log_file: Annotated[Optional[Path], typer.Option("--log-file", help="Path to audit log file (overrides --log)")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Show what would be copied without actually copying")] = False,
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Shortcut for --verbosity verbose")] = False,
):
    """Sync and organize files from source to destination."""
    effective_log_file = log_file
    if log and effective_log_file is None: effective_log_file = get_default_log_file()
    cli_overrides = {
        "source_directory": source, "destination_base": dest, "organization_mode": mode,
        "folder_format": format, "date_source": date_source, "filename_date_format": filename_date_format,
        "include_extensions": extensions, "conflict_policy": conflict, "verification_method": verify,
        "verification_failure_behavior": verify_behavior, "pre_sync_space_check": space_check,
        "max_workers": workers, "buffer_size": buffer_size,
        "output_verbosity": "verbose" if verbose else output_verbosity, "log_file": effective_log_file,
    }

    try: config = merge_config(config_path, **cli_overrides)
    except Exception as e:
        logging.basicConfig(level=logging.ERROR)
        logging.error(f"Configuration error: {e}")
        sys.exit(1)

    # Aggressively clear ALL handlers from ALL loggers in the entire system
    logging.root.handlers = []
    for name in list(logging.root.manager.loggerDict.keys()):
        lgr = logging.getLogger(name)
        lgr.handlers = []
        lgr.propagate = True
    
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    rich_handler = AtomicGridHandler(console=console)
    if config.output_verbosity == "minimal": rich_handler.setLevel(logging.ERROR)
    elif config.output_verbosity == "verbose": rich_handler.setLevel(logging.DEBUG)
    else: rich_handler.setLevel(logging.INFO)
    
    # Attach only to our specific logger
    main_logger = logging.getLogger("copy_that")
    main_logger.addHandler(rich_handler)
    main_logger.propagate = True

    if config.log_file and (not dry_run or config.output_verbosity == "verbose"):
        try:
            log_dir = config.log_file.parent
            log_dir.mkdir(parents=True, exist_ok=True)
            if not os.access(log_dir, os.W_OK): raise PermissionError(f"Directory not writable: {log_dir}")
            file_handler = RotatingFileHandler(config.log_file, maxBytes=config.max_log_size, backupCount=config.log_backup_count)
            file_handler.setLevel(logging.DEBUG)
            file_handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
            root_logger.addHandler(file_handler)
            logger.debug(f"Audit log initialized at {config.log_file}")
        except Exception as e: console.print(f"[yellow]WARNING: Could not initialize log file: {e}[/yellow]")

    # UI VERSION 7 Verification
    logger.debug("[UI VERSION 7] - Synchronous Refresh + Throttle Active")

    logger.info(f"Source: {config.source_directory}")
    logger.info(f"Destination: {config.destination_base}")
    logger.info(f"Mode: {config.organization_mode}")

    if not config.source_directory.exists():
        logger.error(f"Source directory does not exist: {config.source_directory}")
        sys.exit(1)

    if config.pre_sync_space_check:
        logger.info("Performing pre-sync disk space check...")
        perform_space_check(discover_files(config.source_directory, config.include_extensions), config)

    files_to_sync = list(discover_files(config.source_directory, config.include_extensions))
    results: List[FileResult] = []
    stats = SyncStats(total_expected=len(files_to_sync))
    start_time = time.perf_counter()

    from rich.live import Live
    global _live_ui
    _live_ui = Live(LiveSummaryRenderable(stats, start_time, dry_run), console=console, auto_refresh=False)
    
    with _live_ui:
        if dry_run:
            from copy_that.processor import verify_copy, get_unique_path
            for source_file in files_to_sync:
                dest_file = generate_destination_path(source_file, config.source_directory, config.destination_base, config.folder_format, config.organization_mode, config.date_source, config.filename_date_format)
                status = SyncStatus.COPIED
                level = logging.INFO
                if dest_file.exists():
                    level = logging.WARNING
                    if config.conflict_policy == "skip":
                        if config.verification_method == "none":
                            status = SyncStatus.SKIPPED
                        else:
                            if verify_copy(source_file, dest_file, config.verification_method, buffer_size=config.buffer_size):
                                status = SyncStatus.SKIPPED
                            else:
                                status = SyncStatus.OVERWRITTEN
                    elif config.conflict_policy == "overwrite":
                        status = SyncStatus.OVERWRITTEN
                    elif config.conflict_policy == "rename":
                        dest_file = get_unique_path(dest_file)
                        status = SyncStatus.RENAMED

                status_text = status.value.capitalize()
                logger.log(
                    level, 
                    f"[DRY RUN] {status_text}: {source_file} -> {dest_file}",
                    extra={
                        "filename_only": source_file.name,
                        "status_text": status_text,
                        "is_dry_run": True
                    }
                )
                result = FileResult(status, source_file, dest_file, bytes_transferred=source_file.stat().st_size if status != SyncStatus.SKIPPED else 0)
                results.append(result)
                stats.update(result)
        else:
            with ThreadPoolExecutor(max_workers=config.max_workers) as executor:
                future_to_file = {executor.submit(process_single_file, f, config): f for f in files_to_sync}
                for future in as_completed(future_to_file):
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

    _live_ui = None
    end_time = time.perf_counter()
    print_warnings_and_errors(results)
    print_summary(stats, results, end_time - start_time, dry_run=dry_run)

def main():
    def signal_handler(sig, frame):
        sys.stdout.write("\033[r\033[?25h")
        sys.stdout.flush()
        sys.exit(0)
    signal.signal(signal.SIGINT, signal_handler)
    app()

if __name__ == "__main__":
    main()
