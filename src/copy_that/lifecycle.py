import os
import signal
import logging
from pathlib import Path
from typing import Optional, Any
from filelock import FileLock, Timeout

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
    pid_file = lock_file.with_suffix(".pid")
    
    if not pid_file.exists():
        return False
        
    lock = FileLock(str(lock_file), timeout=0)
    try:
        with lock:
            # If we can acquire the lock, the process is dead (stale PID)
            try:
                pid_file.unlink(missing_ok=True)
            except Exception:
                pass
            return False
    except Timeout:
        # Lock is held, daemon is live
        try:
            with open(pid_file, "r") as f:
                pid = int(f.read().strip())
            os.kill(pid, signal.SIGTERM)
            return True
        except (FileNotFoundError, ValueError, ProcessLookupError, PermissionError):
            return False

class ProcessLock:
    def __init__(self, name: str):
        base = get_lock_file(name)
        self._lock = FileLock(str(base), timeout=0)
        self._pid_file = base.with_suffix(".pid")

    def acquire(self) -> bool:
        """Attempt to acquire an exclusive lock. Returns True if successful."""
        try:
            self._lock.acquire()
            self._pid_file.write_text(str(os.getpid()))
            return True
        except Timeout:
            return False
        except PermissionError:
            logger.error(f"Permission denied: Cannot access lock file {self._lock.lock_file}")
            return False

    def release(self):
        """Release the lock."""
        try:
            self._pid_file.unlink(missing_ok=True)
        except Exception:
            pass
        try:
            self._lock.release()
        except Exception:
            pass

    def __enter__(self):
        if not self.acquire():
            raise RuntimeError("Unable to acquire process lock")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()

class GracefulShutdown:
    def __init__(self):
        self.shutdown_requested = False
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)

    def _handle_signal(self, signum, frame):
        logger.info(f"Signal {signum} received. Requesting shutdown...")
        self.shutdown_requested = True
