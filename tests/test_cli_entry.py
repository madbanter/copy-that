from unittest.mock import patch
import pytest
from copy_that.main import main

def test_main_block_execution(monkeypatch):
    # Mock sys.argv to trigger help and exit
    monkeypatch.setattr("sys.argv", ["copy-that", "--help"])
    
    # Typer (via Click) will raise SystemExit(0) after printing help.
    with pytest.raises(SystemExit) as e:
        main()
    
    assert e.value.code == 0
