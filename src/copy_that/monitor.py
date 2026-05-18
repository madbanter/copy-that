import time
import logging
from pathlib import Path
from typing import Callable, List, Set
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from copy_that.lifecycle import GracefulShutdown

logger = logging.getLogger(__name__)

class SyncTrigger:
    """Handles the logic of whether a sync should be triggered."""
    def __init__(self, callback: Callable, debounce_seconds: float):
        self.callback = callback
        self.debounce_seconds = debounce_seconds
        self.last_triggered = 0.0

    def attempt_trigger(self, path: str):
        now = time.time()
        if now - self.last_triggered > self.debounce_seconds:
            logger.info(f"Triggering sync for {path}.")
            self.callback()
            self.last_triggered = now

class DebouncedEventHandler(FileSystemEventHandler):
    def __init__(self, trigger: SyncTrigger):
        self.trigger = trigger

    def on_any_event(self, event):
        if event.is_directory:
            return
        self.trigger.attempt_trigger(str(event.src_path))

class MountMonitor:
    """Handles logic for detecting new mounts."""
    def __init__(self, mount_points: List[Path], on_mount: Callable, whitelist: List[str]):
        self.mount_points = mount_points
        self.on_mount = on_mount
        self.whitelist = whitelist
        self.known_mounts: Set[Path] = set()
        
        # Initialize known mounts
        for mp in self.mount_points:
            if mp.exists():
                for p in mp.iterdir():
                    self.known_mounts.add(p)

    def check(self):
        for mp in self.mount_points:
            if not mp.exists():
                continue
            for p in mp.iterdir():
                if p not in self.known_mounts:
                    self.known_mounts.add(p)
                    logger.info(f"New mount detected: {p}")
                    self.on_mount(p)

class Monitor:
    def __init__(self, shutdown: GracefulShutdown):
        self.shutdown = shutdown
        self.observer = Observer()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.observer.stop()
        self.observer.join()

    def watch_files(self, path: Path, callback: Callable, debounce: float = 5.0):
        trigger = SyncTrigger(callback, debounce)
        handler = DebouncedEventHandler(trigger)
        self.observer.schedule(handler, str(path), recursive=True)

    def watch_mounts(self, mount_points: List[Path], on_mount: Callable, whitelist: List[str]):
        monitor = MountMonitor(mount_points, on_mount, whitelist)
        class MountHandler(FileSystemEventHandler):
            def on_any_event(self, event):
                monitor.check()
        handler = MountHandler()
        self.observer.schedule(handler, str(mount_points[0]), recursive=False)

    def run(self):
        self.observer.start()
        try:
            while not self.shutdown.shutdown_requested:
                time.sleep(1)
        finally:
            self.observer.stop()
            self.observer.join()
