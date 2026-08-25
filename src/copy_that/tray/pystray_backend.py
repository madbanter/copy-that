import pystray
from PIL import Image, ImageDraw
from typing import Callable, Literal, List
from .base import TrayBackend

def create_fallback_icon(state: str) -> Image.Image:
    # A simple fallback image generator since we don't have icon assets yet
    image = Image.new('RGB', (64, 64), color=(255, 255, 255))
    dc = ImageDraw.Draw(image)
    if state == "running":
        dc.ellipse([16, 16, 48, 48], fill="green")
    elif state == "error":
        dc.ellipse([16, 16, 48, 48], fill="red")
    else:
        dc.ellipse([16, 16, 48, 48], fill="gray")
    return image

class PystrayBackend(TrayBackend):
    def __init__(self):
        self._menu_items: List[pystray.MenuItem] = []
        self._icon = pystray.Icon("CopyThat")
        self.set_icon("idle")

    def set_status(self, text: str) -> None:
        self._icon.title = f"CopyThat: {text}"
        if self._icon.HAS_MENU:
            self._icon.update_menu()

    def set_icon(self, state: Literal["idle", "running", "error"]) -> None:
        self._icon.icon = create_fallback_icon(state)
        # We don't have .icns assets yet, so we use fallback icons.
        
    def add_menu_item(self, label: str, callback: Callable) -> None:
        # Pystray callback format is (icon, item)
        def wrapper(icon, item):
            callback()
        self._menu_items.append(pystray.MenuItem(label, wrapper))
        self._icon.menu = pystray.Menu(*self._menu_items)

    def run(self) -> None:
        self._icon.run()

    def stop(self) -> None:
        self._icon.stop()
