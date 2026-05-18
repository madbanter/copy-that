import os
import signal
import logging
import fcntl
from pathlib import Path
from typing import Optional, Any

logger = logging.getLogger(__name__)

# The OS automatically releases advisory locks if the process exits,
# even if it crashes, eliminating stale PID file issues.
def get_lock_file(name: str) -> Path:
    config_dir = Path.home() / ".config" / "copy-that"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir / f"{name}.lock"

def stop_process(name: str) -> bool:
    """Reads PID from lock file and sends SIGTERM to the process."""
    lock_file = get_lock_file(name)
    if not lock_file.exists():
        return False
    try:
        with open(lock_file, "r") as f:
            pid = int(f.read().strip())
        os.kill(pid, signal.SIGTERM)
        return True
    except (FileNotFoundError, ValueError, ProcessLookupError, PermissionError):
        return False

class ProcessLock:
    def __init__(self, name: str):
        self.lock_file = get_lock_file(name)
        self.file: Optional[Any] = None

    def acquire(self) -> bool:
        """Attempt to acquire an exclusive lock. Returns True if successful."""
        try:
            self.file = open(self.lock_file, "w")
            fcntl.flock(self.file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            # Store the PID in the lock file for visibility
            self.file.write(str(os.getpid()))
            self.file.flush()
            return True
        except PermissionError:
            logger.error(f"Permission denied: Cannot access lock file {self.lock_file}")
            return False
        except (IOError, OSError):
            if self.file:
                self.file.close()
                self.file = None
            return False

    def release(self):
        """Release the lock."""
        if self.file:
            try:
                fcntl.flock(self.file.fileno(), fcntl.LOCK_UN)
                self.file.close()
            except Exception:
                pass
            self.file = None

class GracefulShutdown:
    def __init__(self):
        self.shutdown_requested = False
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)

    def _handle_signal(self, signum, frame):
        logger.info(f"Signal {signum} received. Requesting shutdown...")
        self.shutdown_requested = True
