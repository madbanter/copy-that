import logging
from pathlib import Path
from copy_that.main import format_bytes, print_summary
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

def test_print_summary_with_failures(caplog):
    results = [
        FileResult(SyncStatus.COPIED, Path("src/a.jpg"), Path("dest/a.jpg"), bytes_transferred=100),
        FileResult(SyncStatus.FAILED, Path("src/b.jpg"), Path("dest/b.jpg"), error_message="Disk full"),
        FileResult(SyncStatus.SKIPPED, Path("src/c.jpg"), Path("dest/c.jpg")),
        FileResult(SyncStatus.OVERWRITTEN, Path("src/d.jpg"), Path("dest/d.jpg"), bytes_transferred=200),
        FileResult(SyncStatus.RENAMED, Path("src/e.jpg"), Path("dest/e_1.jpg"), bytes_transferred=300),
    ]
    
    with caplog.at_level(logging.INFO):
        print_summary(results, elapsed_time=2.0)
    
    assert "Sync Summary" in caplog.text
    assert "Total Files Processed: 5" in caplog.text
    assert "Copied:" in caplog.text
    assert "3" in caplog.text # Aggregated count
    assert "Skipped:" in caplog.text
    assert "1" in caplog.text
    assert "Failed:" in caplog.text
    assert "Total Data" in caplog.text
    assert "600.00 B" in caplog.text
    assert "Failures:" in caplog.text
    assert "b.jpg: Disk full" in caplog.text
    assert "Average Speed:" in caplog.text
    assert "300.00 B/s" in caplog.text

def test_print_summary_dry_run(caplog):
    results = [
        FileResult(SyncStatus.COPIED, Path("src/a.jpg"), Path("dest/a.jpg"), bytes_transferred=1000),
        FileResult(SyncStatus.SKIPPED, Path("src/b.jpg"), Path("dest/b.jpg")),
    ]
    
    with caplog.at_level(logging.INFO):
        print_summary(results, elapsed_time=0.5, dry_run=True)
    
    assert "Sync Summary (DRY RUN)" in caplog.text
    assert "Would copy:" in caplog.text
    assert "1" in caplog.text
    assert "Would skip:" in caplog.text
    assert "Data to transfer" in caplog.text
    assert "1000.00 B" in caplog.text
    assert "Average Speed" not in caplog.text

def test_print_summary_empty(caplog):
    with caplog.at_level(logging.INFO):
        print_summary([], elapsed_time=1.0)
    
    assert "Total Files Processed: 0" in caplog.text
    assert "Average Speed" not in caplog.text
