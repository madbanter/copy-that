import pytest
from pathlib import Path
from copy_that.main import truncate_middle, print_warnings_and_errors
from copy_that.processor import FileResult, SyncStatus

def test_truncate_middle_no_truncation():
    assert truncate_middle("short", 10) == "short"
    assert truncate_middle("exactly_10", 10) == "exactly_10"

def test_truncate_middle_basic():
    # "longfilename.txt" is 16 chars. 
    # max_length=10. remaining = 10-3 = 7. left = 3, right = 4.
    # text[:3] = "lon", text[-4:] = ".txt"
    assert truncate_middle("longfilename.txt", 10) == "lon....txt"

def test_truncate_middle_short_max():
    assert truncate_middle("filename.txt", 3) == "..."
    assert truncate_middle("filename.txt", 2) == ".."
    assert truncate_middle("filename.txt", 1) == "."

def test_truncate_middle_odd_remaining():
    # length 20, max 11. remaining = 8. left 4, right 4.
    assert truncate_middle("12345678901234567890", 11) == "1234...7890"

def test_print_warnings_and_errors_no_data(capsys):
    print_warnings_and_errors([])
    captured = capsys.readouterr()
    assert captured.err == ""

def test_print_warnings_and_errors_with_data(capsys):
    results = [
        FileResult(SyncStatus.COPIED, Path("src/ok.txt"), Path("dest/ok.txt")),
        FileResult(SyncStatus.SKIPPED, Path("src/skipped.txt"), Path("dest/skipped.txt")),
        FileResult(SyncStatus.FAILED, Path("src/failed.txt"), Path("dest/failed.txt"), error_message="Disk full"),
        FileResult(SyncStatus.RENAMED, Path("src/conflict.txt"), Path("dest/conflict_1.txt")),
    ]
    
    print_warnings_and_errors(results)
    captured = capsys.readouterr()
    
    # console.print defaults to stderr=True in main.py
    output = captured.err
    
    assert "Warnings:" in output
    assert "Errors:" in output
    assert "SKIPPED: src/skipped.txt -> dest/skipped.txt" in output
    assert "FAILED: src/failed.txt -> dest/failed.txt" in output
    assert "Error: Disk full" in output
    assert "RENAMED: src/conflict.txt -> dest/conflict_1.txt" in output
    assert "ok.txt" not in output # Copied should be hidden
    assert "----------" not in output # Dashed line should be gone
