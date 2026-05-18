import os
import signal
import json
import logging
import psutil
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

def get_pid_file(name: str) -> Path:
    """Get the path to the PID file for a background process."""
    # Use Path.home() to allow overriding in tests.
    # In production this defaults to ~/.config/copy-that,
    # but tests mock Path.home() so it goes into the temp directory.
    config_dir = Path.home() / ".config" / "copy-that"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir / f"{name}.pid"

def write_pid_file(name: str, command: str):
    """Write process information to a PID file."""
    pid_file = get_pid_file(name)
    info = {
        "pid": os.getpid(),
        "started_at": psutil.Process().create_time(),
        "command": command
    }
    with open(pid_file, "w") as f:
        json.dump(info, f)

def remove_pid_file(name: str):
    """Remove the PID file."""
    pid_file = get_pid_file(name)
    if pid_file.exists():
        pid_file.unlink()

def is_process_running(name: str) -> Optional[int]:
    """Check if a background process is running and return its PID if so."""
    pid_file = get_pid_file(name)
    if not pid_file.exists():
        return None
        
    try:
        with open(pid_file, "r") as f:
            info = json.load(f)
            pid = info["pid"]
            started_at = info["started_at"]
            
        if psutil.pid_exists(pid):
            proc = psutil.Process(pid)
            # Verify PID reuse
            if proc.create_time() == started_at:
                return pid
        
        # PID stale or reused
        remove_pid_file(name)
    except (json.JSONDecodeError, KeyError, psutil.NoSuchProcess):
        remove_pid_file(name)
        
    return None

def stop_process(name: str) -> bool:
    """Stop a running background process."""
    pid = is_process_running(name)
    if pid:
        try:
            os.kill(pid, signal.SIGTERM)
            return True
        except ProcessLookupError:
            return False
    return False

class GracefulShutdown:
    def __init__(self):
        self.shutdown_requested = False
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)

    def _handle_signal(self, signum, frame):
        logger.info(f"Signal {signum} received. Requesting shutdown...")
        self.shutdown_requested = True
