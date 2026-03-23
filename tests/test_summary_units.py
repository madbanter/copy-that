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
    assert "Copied:            3" in caplog.text # COPIED + OVERWRITTEN + RENAMED
    assert "Skipped:           1" in caplog.text
    assert "Failed:            1" in caplog.text
    assert "Failures:" in caplog.text
    assert "b.jpg: Disk full" in caplog.text
    assert "Average Speed:         300.00 B/s" in caplog.text # (100+200+300)/2.0

def test_print_summary_empty(caplog):
    with caplog.at_level(logging.INFO):
        print_summary([], elapsed_time=1.0)
    
    assert "Total Files Processed: 0" in caplog.text
    assert "Average Speed" not in caplog.text
