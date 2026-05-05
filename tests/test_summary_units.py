import logging
import time
from pathlib import Path
from copy_that.main import format_bytes, print_summary, SyncStats, LiveSummaryRenderable
from copy_that.processor import FileResult, SyncStatus

def test_format_bytes():
    assert format_bytes(0) == "0.00 B"
    assert format_bytes(500) == "500.00 B"
    assert format_bytes(1024) == "1.00 KB"
    assert format_bytes(1024 * 1024) == "1.00 MB"
    assert format_bytes(1024 * 1024 * 1024) == "1.00 GB"
    assert format_bytes(1024 * 1024 * 1024 * 1024) == "1.00 TB"
    assert format_bytes(1024 * 1024 * 1024 * 1024 * 1024) == "1.00 PB"
    # Test very large number
    assert format_bytes(1024 * 1024 * 1024 * 1024 * 1024 * 1024) == "1024.00 PB"

def test_sync_stats_aggregation():
    stats = SyncStats(total_expected=3)
    
    # 1. Normal copy
    stats.update(FileResult(SyncStatus.COPIED, Path("a"), Path("a"), bytes_transferred=100))
    # 2. Failed but retried successfully (OVERWRITTEN status used during retry)
    stats.update(FileResult(SyncStatus.OVERWRITTEN, Path("b"), Path("b"), bytes_transferred=200, retried=True))
    # 3. Permanent Failure
    stats.update(FileResult(SyncStatus.FAILED, Path("c"), Path("c"), error_message="fail"))
    
    assert stats.processed == 3
    assert stats.transferred_count == 2 # COPIED + OVERWRITTEN
    assert stats.failed_count == 1
    assert stats.retried_count == 1
    assert stats.total_bytes == 300
    assert stats.total_expected == 3

def test_generate_live_summary_normal():
    stats = SyncStats(total_expected=10)
    stats.processed = 5
    stats.transferred_count = 4
    stats.failed_count = 1

    renderable = LiveSummaryRenderable(stats, start_time=time.perf_counter(), dry_run=False)
    table = renderable.__rich__()
    # Verify columns
    column_names = [col.header for col in table.columns]
    assert "Transferred" in column_names
    assert "Progress" in column_names
    
    assert len(table.columns) == 5
def test_generate_live_summary_dry_run():
    stats = SyncStats(total_expected=10)
    stats.processed = 5
    stats.failed_count = 0

    renderable = LiveSummaryRenderable(stats, start_time=time.perf_counter(), dry_run=True)
    table = renderable.__rich__()
    # Verify columns - Transferred should be missing
    column_names = [col.header for col in table.columns]
    assert "Transferred" not in column_names
    assert "Progress" in column_names
    assert "Processed" in column_names
    
    # Verify column count
    assert len(table.columns) == 4
def test_print_summary_with_failures(capsys):
    results = [
        FileResult(SyncStatus.COPIED, Path("src/a.jpg"), Path("dest/a.jpg"), bytes_transferred=100),
        FileResult(SyncStatus.FAILED, Path("src/b.jpg"), Path("dest/b.jpg"), error_message="Disk full"),
        FileResult(SyncStatus.SKIPPED, Path("src/c.jpg"), Path("dest/c.jpg")),
        FileResult(SyncStatus.OVERWRITTEN, Path("src/d.jpg"), Path("dest/d.jpg"), bytes_transferred=200),
        FileResult(SyncStatus.RENAMED, Path("src/e.jpg"), Path("dest/e_1.jpg"), bytes_transferred=300),
    ]
    
    stats = SyncStats(total_expected=5)
    for r in results:
        stats.update(r)

    print_summary(stats, results, elapsed_time=2.0)
    
    captured = capsys.readouterr()
    assert "Sync Summary" in captured.err
    assert "Total Files Processed" in captured.err
    assert "Copied" in captured.err
    assert "3" in captured.err
    assert "Skipped" in captured.err
    assert "1" in captured.err
    assert "Failed" in captured.err
    assert "Total Data" in captured.err
    assert "600.00 B" in captured.err
    assert "Failures:" in captured.err
    assert "b.jpg" in captured.err
    assert "Disk full" in captured.err
    assert "Average Speed:" in captured.err
    assert "300.00 B/s" in captured.err

def test_print_summary_dry_run(capsys):
    results = [
        FileResult(SyncStatus.COPIED, Path("src/a.jpg"), Path("dest/a.jpg"), bytes_transferred=1000),
        FileResult(SyncStatus.SKIPPED, Path("src/b.jpg"), Path("dest/b.jpg")),
    ]
    
    stats = SyncStats(total_expected=2)
    for r in results:
        stats.update(r)

    print_summary(stats, results, elapsed_time=0.5, dry_run=True)
    
    captured = capsys.readouterr()
    assert "Sync Summary (DRY RUN)" in captured.err
    assert "Would copy" in captured.err
    assert "1" in captured.err
    assert "Would skip" in captured.err
    assert "Data to transfer" in captured.err
    assert "1000.00 B" in captured.err
    assert "Average Speed" not in captured.err

def test_print_summary_empty(capsys):
    stats = SyncStats(total_expected=0)
    print_summary(stats, [], elapsed_time=1.0)
    
    captured = capsys.readouterr()
    assert "Total Files Processed" in captured.err
    assert "0" in captured.err
    assert "Average Speed" not in captured.err
