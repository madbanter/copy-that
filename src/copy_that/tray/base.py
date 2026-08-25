from abc import ABC, abstractmethod
from typing import Callable, Literal

class TrayBackend(ABC):
    @abstractmethod
    def set_status(self, text: str) -> None: ...

    @abstractmethod
    def set_icon(self, state: Literal["idle", "running", "error"]) -> None: ...

    @abstractmethod
    def add_menu_item(self, label: str, callback: Callable) -> None: ...

    @abstractmethod
    def run(self) -> None: ...  # Blocks; runs the platform event loop on the main thread

    @abstractmethod
    def stop(self) -> None: ...
