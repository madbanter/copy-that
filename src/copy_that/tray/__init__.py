import os
import sys
import json
import time
import threading
import subprocess
from pathlib import Path
from typing import Optional
from filelock import FileLock, Timeout

from .base import TrayBackend

def get_tray_backend() -> TrayBackend:
    from .pystray_backend import PystrayBackend
    return PystrayBackend()

def is_daemon_running() -> bool:
    from copy_that.lifecycle import get_lock_file
    lock_file = get_lock_file("watcher")
    lock = FileLock(str(lock_file), timeout=0)
    try:
        lock.acquire()
        lock.release()
        return False
    except Timeout:
        return True

def get_log_file() -> Path:
    from copy_that.config import get_default_log_file
    return get_default_log_file()

def open_file(path: Path):
    if sys.platform == "win32":
        os.startfile(path)
    elif sys.platform == "darwin":
        subprocess.run(["open", str(path)])
    else:
        subprocess.run(["xdg-open", str(path)])

class TrayApp:
    def __init__(self):
        self.backend = get_tray_backend()
        self.setup_menu()
        self._running = True
        
        # Start status polling thread
        self.poll_thread = threading.Thread(target=self._poll_status, daemon=True)
        self.poll_thread.start()

    def setup_menu(self):
        self.backend.add_menu_item("Start Daemon", self.start_daemon)
        self.backend.add_menu_item("Stop Daemon", self.stop_daemon)
        self.backend.add_menu_item("Open Log", self.open_log)
        self.backend.add_menu_item("Quit", self.quit)

    def start_daemon(self):
        # We need to run the daemon. If running via script, invoke uv or python.
        # If running as standalone binary, invoke the CLI binary.
        # For simplicity in MVP, we just use sys.executable -m copy_that.main if possible,
        # or call the CLI.
        if getattr(sys, 'frozen', False):
            # We are in a PyInstaller bundle
            cli_path = Path(sys.executable).parent / "copy-that"
            if sys.platform == "win32":
                cli_path = cli_path.with_suffix(".exe")
            if cli_path.exists():
                subprocess.Popen([str(cli_path)])
            else:
                print(f"Could not find CLI binary at {cli_path}")
        else:
            subprocess.Popen([sys.executable, "-m", "copy_that.main"])

    def stop_daemon(self):
        from copy_that.lifecycle import stop_process
        stop_process("watcher")

    def open_log(self):
        log_file = get_log_file()
        if log_file.exists():
            open_file(log_file)

    def quit(self):
        self._running = False
        self.backend.stop()

    def _poll_status(self):
        last_state = None
        while self._running:
            running = is_daemon_running()
            state = "running" if running else "idle"
            if state != last_state:
                self.backend.set_icon(state)
                self.backend.set_status(state.capitalize())
                last_state = state
            time.sleep(1)

    def run(self):
        self.backend.run()

def main():
    app = TrayApp()
    app.run()

if __name__ == "__main__":
    main()
